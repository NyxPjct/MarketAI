from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User, Plan, Subscription, BillingTransaction, ProviderPlan

MP_BASE = "https://api.mercadopago.com"
STRIPE_BASE = "https://api.stripe.com/v1"
PAYPAL_LIVE = "https://api-m.paypal.com"
PAYPAL_SANDBOX = "https://api-m.sandbox.paypal.com"

LATAM_MP_COUNTRIES = {"BR", "AR", "CL", "CO", "MX", "PE", "UY"}
ZERO_DECIMAL = {"JPY", "KRW"}


def utcnow():
    return datetime.now(timezone.utc)


def _aware(dt):
    return dt if (dt is None or dt.tzinfo) else dt.replace(tzinfo=timezone.utc)


def _mp_headers(extra=None):
    h = {"Authorization": f"Bearer {settings.mercado_pago_token}", "Content-Type": "application/json"}
    h.update(extra or {})
    return h


def _stripe_headers():
    return {"Authorization": f"Bearer {settings.stripe_secret_key}", "Content-Type": "application/x-www-form-urlencoded"}


def _paypal_base():
    return PAYPAL_LIVE if settings.paypal_mode.lower() == "live" else PAYPAL_SANDBOX


def _plan_env_prefix(plan_code: str) -> str:
    return f"PLAN_{plan_code.upper()}_PRICE_"


def plan_price(plan: Plan, currency: str) -> float:
    """Commercial price per currency. Explicit env values win; sensible defaults follow."""
    currency = (currency or "BRL").upper()
    raw = os.getenv(_plan_env_prefix(plan.code) + currency, "").strip()
    if raw:
        try:
            return round(float(raw), 2)
        except ValueError:
            pass

    defaults = {
        "essencial": {"BRL": 49.90, "USD": 9.99, "EUR": 9.49, "GBP": 7.99, "CAD": 13.49, "MXN": 179.00, "JPY": 1490},
        "pro": {"BRL": 99.90, "USD": 19.99, "EUR": 18.99, "GBP": 15.99, "CAD": 26.99, "MXN": 359.00, "JPY": 2990},
        "business": {"BRL": 199.90, "USD": 39.99, "EUR": 37.99, "GBP": 31.99, "CAD": 53.99, "MXN": 719.00, "JPY": 5990},
    }
    extras = {
        "essencial": {"KRW": 13900, "AUD": 14.99, "NZD": 16.49, "CHF": 8.99, "SEK": 99.00},
        "pro": {"KRW": 27900, "AUD": 29.99, "NZD": 32.99, "CHF": 17.99, "SEK": 199.00},
        "business": {"KRW": 55900, "AUD": 59.99, "NZD": 65.99, "CHF": 35.99, "SEK": 399.00},
    }
    for code,vals in extras.items(): defaults.setdefault(code,{}).update(vals)
    if currency == "BRL":
        return round(plan.price_brl, 2)
    return float(defaults.get(plan.code, {}).get(currency, defaults.get(plan.code, {}).get("USD", 9.99)))


def currency_for_country(country: str) -> str:
    return {
        "BR": "BRL", "US": "USD", "FR": "EUR", "DE": "EUR", "ES": "EUR", "IT": "EUR", "PT": "EUR",
        "GB": "GBP", "CA": "CAD", "MX": "MXN", "JP": "JPY", "KR": "KRW", "AR": "USD", "CL": "USD",
        "CO": "USD", "PE": "USD", "UY": "USD", "AU": "AUD", "NZ": "NZD", "CH": "CHF", "SE": "SEK",
    }.get((country or "").upper(), "USD")


def payment_methods(country_code: str) -> list[dict]:
    c = (country_code or "BR").upper()
    currency = currency_for_country(c)
    methods = []
    if c == "BR" and settings.mercado_pago_token:
        methods.append({
            "id": "pix", "provider": "mercadopago", "name": "Pix", "currency": "BRL", "recurring": False,
            "description": "Pagamento instantâneo. Libera 30 dias e a renovação é manual.", "badge": "BRASIL",
        })
    if settings.stripe_secret_key:
        methods.append({
            "id": "card", "provider": "stripe", "name": "Cartão de crédito ou débito", "currency": currency,
            "recurring": True, "description": "Checkout internacional por cartão, sujeito à bandeira, banco e país do emissor.", "badge": "GLOBAL",
        })
    if settings.paypal_client_id and settings.paypal_client_secret:
        paypal_currency = currency if currency in {"USD","EUR","GBP","CAD","AUD","BRL","MXN","JPY"} else "USD"
        methods.append({
            "id": "paypal", "provider": "paypal", "name": "PayPal", "currency": paypal_currency,
            "recurring": True, "description": "Assinatura recorrente pelo PayPal nos países e moedas suportados pela conta.", "badge": "GLOBAL",
        })
    if c == "BR" and settings.mercado_pago_token:
        methods.append({
            "id": "mercadopago", "provider": "mercadopago", "name": "Mercado Pago", "currency": "BRL",
            "recurring": True, "description": "Assinatura recorrente pelo Mercado Pago, conforme meios disponíveis na conta brasileira.", "badge": "LATAM",
        })
    return methods


def _new_tx(db: Session, user: User, plan: Plan, provider: str, method: str, amount: float, currency: str, period_days=30):
    tx = BillingTransaction(
        user_id=user.id, plan_code=plan.code, provider=provider, payment_method=method, status="pending",
        amount=amount, currency=currency, period_days=period_days,
    )
    db.add(tx); db.commit(); db.refresh(tx)
    return tx


def _sub_for_user(db: Session, user: User, plan_code: str, provider: str):
    sub = user.subscription
    if not sub:
        sub = Subscription(user_id=user.id, plan_code=plan_code); db.add(sub)
    sub.plan_code = plan_code
    sub.provider = provider
    return sub


# ---------------- Mercado Pago recurring ----------------
async def create_mp_subscription(db: Session, user: User, plan: Plan):
    if not settings.mercado_pago_token:
        raise RuntimeError("mercadopago_not_configured")
    amount = plan_price(plan, "BRL")
    tx = _new_tx(db, user, plan, "mercadopago", "mercadopago", amount, "BRL")
    payload = {
        "reason": f"MarketAI {plan.name}",
        "external_reference": f"{user.id}:{plan.code}:{tx.id}",
        "payer_email": user.email,
        "auto_recurring": {"frequency": 1, "frequency_type": "months", "transaction_amount": round(amount, 2), "currency_id": "BRL"},
        "back_url": settings.public_app_url + "/assinatura",
        "status": "pending",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(MP_BASE + "/preapproval", headers=_mp_headers(), json=payload)
    if r.status_code >= 400:
        tx.status = "failed"; db.commit()
        raise RuntimeError(f"mercadopago_error:{r.status_code}:{r.text[:300]}")
    data = r.json()
    tx.provider_object_id = str(data.get("id") or "")
    tx.checkout_url = data.get("init_point")
    tx.status = str(data.get("status") or "pending")
    db.commit()
    return {"checkout_url": tx.checkout_url, "billing_id": tx.id, "provider": "mercadopago", "payment_method": "mercadopago", "status": tx.status}


async def fetch_mp_preapproval(preapproval_id: str):
    if not settings.mercado_pago_token: raise RuntimeError("mercadopago_not_configured")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(MP_BASE + f"/preapproval/{preapproval_id}", headers=_mp_headers())
    if r.status_code >= 400: raise RuntimeError(f"mercadopago_lookup_error:{r.status_code}")
    return r.json()


def sync_mp_subscription(db: Session, data: dict):
    provider_id = str(data.get("id") or "")
    external = str(data.get("external_reference") or "")
    sub = db.query(Subscription).filter_by(provider="mercadopago", provider_subscription_id=provider_id).first()
    user = None; plan_code = ""
    if external:
        bits = external.split(":")
        if len(bits) >= 2:
            user = db.get(User, bits[0]); plan_code = bits[1]
    if not sub and user:
        sub = _sub_for_user(db, user, plan_code or "essencial", "mercadopago")
        sub.provider_subscription_id = provider_id
    if not sub: return None
    mp_status = str(data.get("status") or "").lower()
    sub.status = {"authorized":"active", "paused":"past_due", "cancelled":"canceled", "cancelled_by_user":"canceled", "pending":"pending"}.get(mp_status, mp_status or "pending")
    if sub.status == "active":
        next_date = data.get("next_payment_date")
        try: sub.current_period_end = datetime.fromisoformat(next_date.replace("Z", "+00:00")) if next_date else utcnow() + timedelta(days=35)
        except Exception: sub.current_period_end = utcnow() + timedelta(days=35)
        if external:
            bits = external.split(":")
            if len(bits) >= 3:
                tx = db.get(BillingTransaction, bits[2])
                if tx and tx.credited_at is None:
                    tx.status = "approved"; tx.credited_at = utcnow()
    db.commit(); return sub


async def cancel_mp_subscription(preapproval_id: str):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.put(MP_BASE + f"/preapproval/{preapproval_id}", headers=_mp_headers(), json={"status":"cancelled"})
    if r.status_code >= 400: raise RuntimeError(f"mercadopago_cancel_error:{r.status_code}:{r.text[:200]}")
    return r.json()


# ---------------- Mercado Pago Pix (one-time access) ----------------
async def create_pix_payment(db: Session, user: User, plan: Plan):
    if not settings.mercado_pago_token: raise RuntimeError("mercadopago_not_configured")
    amount = plan_price(plan, "BRL")
    tx = _new_tx(db, user, plan, "mercadopago", "pix", amount, "BRL", period_days=30)
    payload = {
        "transaction_amount": round(amount, 2),
        "description": f"MarketAI {plan.name} - 30 dias",
        "payment_method_id": "pix",
        "payer": {"email": user.email},
        "external_reference": f"marketai:{tx.id}:{user.id}:{plan.code}",
    }
    if settings.mercado_pago_webhook_url:
        payload["notification_url"] = settings.mercado_pago_webhook_url
    headers = _mp_headers({"X-Idempotency-Key": tx.id})
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(MP_BASE + "/v1/payments", headers=headers, json=payload)
    if r.status_code >= 400:
        tx.status = "failed"; db.commit()
        raise RuntimeError(f"pix_error:{r.status_code}:{r.text[:300]}")
    data = r.json(); poi = ((data.get("point_of_interaction") or {}).get("transaction_data") or {})
    tx.provider_object_id = str(data.get("id") or "")
    tx.status = str(data.get("status") or "pending")
    tx.checkout_url = poi.get("ticket_url") or ""
    db.commit()
    return {
        "provider":"mercadopago", "payment_method":"pix", "billing_id":tx.id, "payment_id":tx.provider_object_id,
        "status":tx.status, "checkout_url":tx.checkout_url, "qr_code":poi.get("qr_code"), "qr_code_base64":poi.get("qr_code_base64"),
        "expires_note":"O Pix libera 30 dias após confirmação e não renova automaticamente.",
    }


async def fetch_mp_payment(payment_id: str):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(MP_BASE + f"/v1/payments/{payment_id}", headers=_mp_headers())
    if r.status_code >= 400: raise RuntimeError(f"mercadopago_payment_lookup_error:{r.status_code}")
    return r.json()


def sync_pix_payment(db: Session, data: dict):
    pid = str(data.get("id") or "")
    tx = db.query(BillingTransaction).filter_by(provider="mercadopago", payment_method="pix", provider_object_id=pid).first()
    if not tx:
        ext = str(data.get("external_reference") or "")
        if ext.startswith("marketai:"):
            bits = ext.split(":")
            if len(bits) >= 2: tx = db.get(BillingTransaction, bits[1])
    if not tx: return None
    status = str(data.get("status") or "pending").lower(); tx.status = status
    if status == "approved" and tx.credited_at is None:
        user = db.get(User, tx.user_id)
        sub = _sub_for_user(db, user, tx.plan_code, "pix")
        base = max(utcnow(), _aware(sub.current_period_end) or utcnow())
        sub.status = "active"; sub.provider_subscription_id = pid; sub.current_period_end = base + timedelta(days=tx.period_days or 30)
        tx.credited_at = utcnow()
    db.commit(); return tx


# ---------------- Stripe cards ----------------
def _stripe_minor(amount: float, currency: str) -> int:
    return int(round(amount if currency.upper() in ZERO_DECIMAL else amount * 100))


async def create_stripe_checkout(db: Session, user: User, plan: Plan, currency: str):
    if not settings.stripe_secret_key: raise RuntimeError("stripe_not_configured")
    currency = (currency or "USD").upper(); amount = plan_price(plan, currency)
    tx = _new_tx(db, user, plan, "stripe", "card", amount, currency)
    payload = {
        "mode":"subscription",
        "success_url": settings.public_app_url + "/assinatura?provider=stripe&success=1&session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": settings.public_app_url + "/assinatura?provider=stripe&canceled=1",
        "client_reference_id": user.id,
        "customer_email": user.email,
        "metadata[user_id]": user.id,
        "metadata[plan_code]": plan.code,
        "metadata[billing_id]": tx.id,
        "subscription_data[metadata][user_id]": user.id,
        "subscription_data[metadata][plan_code]": plan.code,
        "subscription_data[metadata][billing_id]": tx.id,
        "line_items[0][price_data][currency]": currency.lower(),
        "line_items[0][price_data][unit_amount]": str(_stripe_minor(amount, currency)),
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][price_data][product_data][name]": f"MarketAI {plan.name}",
        "line_items[0][quantity]": "1",
        "payment_method_types[0]": "card",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(STRIPE_BASE + "/checkout/sessions", headers=_stripe_headers(), content=urlencode(payload))
    if r.status_code >= 400:
        tx.status = "failed"; db.commit(); raise RuntimeError(f"stripe_error:{r.status_code}:{r.text[:300]}")
    data = r.json(); tx.provider_object_id = str(data.get("id") or ""); tx.checkout_url = data.get("url") or ""; tx.status = "checkout_created"; db.commit()
    return {"provider":"stripe", "payment_method":"card", "billing_id":tx.id, "checkout_url":tx.checkout_url, "status":tx.status, "currency":currency, "amount":amount}


async def fetch_stripe_subscription(subscription_id: str):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(STRIPE_BASE + f"/subscriptions/{subscription_id}", headers={"Authorization": f"Bearer {settings.stripe_secret_key}"})
    if r.status_code >= 400: raise RuntimeError(f"stripe_lookup_error:{r.status_code}")
    return r.json()


async def fetch_stripe_checkout_session(session_id: str):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(STRIPE_BASE + f"/checkout/sessions/{session_id}", headers={"Authorization": f"Bearer {settings.stripe_secret_key}"})
    if r.status_code >= 400: raise RuntimeError(f"stripe_checkout_lookup_error:{r.status_code}")
    return r.json()


def sync_stripe_subscription(db: Session, data: dict):
    sid = str(data.get("id") or ""); metadata = data.get("metadata") or {}; user_id = metadata.get("user_id"); plan_code = metadata.get("plan_code")
    sub = db.query(Subscription).filter_by(provider="stripe", provider_subscription_id=sid).first()
    user = db.get(User, user_id) if user_id else None
    if not sub and user:
        sub = _sub_for_user(db, user, plan_code or "essencial", "stripe"); sub.provider_subscription_id = sid
    if not sub: return None
    status = str(data.get("status") or "pending").lower()
    sub.status = {"active":"active", "trialing":"active", "past_due":"past_due", "unpaid":"past_due", "canceled":"canceled", "incomplete":"pending", "incomplete_expired":"canceled", "paused":"past_due"}.get(status, status)
    period_end = data.get("current_period_end")
    if not period_end:
        items = ((data.get("items") or {}).get("data") or [])
        if items: period_end = items[0].get("current_period_end")
    if period_end:
        try: sub.current_period_end = datetime.fromtimestamp(int(period_end), tz=timezone.utc)
        except Exception: pass
    if sub.status == "active":
        billing_id = metadata.get("billing_id")
        if billing_id:
            tx = db.get(BillingTransaction, billing_id)
            if tx and tx.credited_at is None:
                tx.status = "active"; tx.credited_at = utcnow()
    db.commit(); return sub


async def cancel_stripe_subscription(subscription_id: str):
    payload = urlencode({"cancel_at_period_end":"true"})
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(STRIPE_BASE + f"/subscriptions/{subscription_id}", headers=_stripe_headers(), content=payload)
    if r.status_code >= 400: raise RuntimeError(f"stripe_cancel_error:{r.status_code}:{r.text[:200]}")
    return r.json()


def verify_stripe_webhook(raw: bytes, signature: str) -> bool:
    secret = settings.stripe_webhook_secret
    if not secret: return settings.allow_unverified_webhooks
    fields = {}
    for piece in (signature or "").split(","):
        if "=" in piece:
            k, v = piece.split("=", 1); fields.setdefault(k, []).append(v)
    try: ts = int((fields.get("t") or ["0"])[0])
    except Exception: return False
    if abs(time.time() - ts) > 300: return False
    signed = f"{ts}.".encode() + raw
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, v) for v in fields.get("v1", []))


# ---------------- PayPal ----------------
async def paypal_access_token() -> str:
    if not (settings.paypal_client_id and settings.paypal_client_secret): raise RuntimeError("paypal_not_configured")
    basic = base64.b64encode(f"{settings.paypal_client_id}:{settings.paypal_client_secret}".encode()).decode()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(_paypal_base() + "/v1/oauth2/token", headers={"Authorization":f"Basic {basic}", "Content-Type":"application/x-www-form-urlencoded"}, content="grant_type=client_credentials")
    if r.status_code >= 400: raise RuntimeError(f"paypal_auth_error:{r.status_code}")
    return r.json().get("access_token")


async def _paypal_request(method: str, path: str, json_data=None):
    token = await paypal_access_token()
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.request(method, _paypal_base()+path, headers={"Authorization":f"Bearer {token}", "Content-Type":"application/json", "Accept":"application/json", "PayPal-Request-Id":secrets.token_hex(16)}, json=json_data)
    if r.status_code >= 400: raise RuntimeError(f"paypal_error:{r.status_code}:{r.text[:300]}")
    return r.json() if r.content else {}


async def ensure_paypal_plan(db: Session, plan: Plan, currency: str) -> str:
    currency = currency.upper()
    row = db.query(ProviderPlan).filter_by(provider="paypal", app_plan_code=plan.code, currency=currency).first()
    if row and row.provider_plan_id: return row.provider_plan_id
    product = await _paypal_request("POST", "/v1/catalogs/products", {
        "name": f"MarketAI {plan.name}", "description":"MarketAI commercial subscription", "type":"SERVICE", "category":"SOFTWARE"
    })
    amount = plan_price(plan, currency)
    amount_text = f"{amount:.0f}" if currency in ZERO_DECIMAL else f"{amount:.2f}"
    pp = await _paypal_request("POST", "/v1/billing/plans", {
        "product_id": product["id"], "name": f"MarketAI {plan.name} {currency}", "description": f"MarketAI {plan.name} monthly",
        "status":"ACTIVE",
        "billing_cycles":[{"frequency":{"interval_unit":"MONTH","interval_count":1}, "tenure_type":"REGULAR", "sequence":1, "total_cycles":0, "pricing_scheme":{"fixed_price":{"value":amount_text,"currency_code":currency}}}],
        "payment_preferences":{"auto_bill_outstanding":True, "payment_failure_threshold":3}
    })
    row = ProviderPlan(provider="paypal", app_plan_code=plan.code, currency=currency, provider_product_id=product.get("id"), provider_plan_id=pp.get("id"))
    db.add(row); db.commit(); return row.provider_plan_id


async def create_paypal_subscription(db: Session, user: User, plan: Plan, currency: str):
    currency = (currency or "USD").upper(); amount = plan_price(plan, currency)
    tx = _new_tx(db, user, plan, "paypal", "paypal", amount, currency)
    provider_plan_id = await ensure_paypal_plan(db, plan, currency)
    data = await _paypal_request("POST", "/v1/billing/subscriptions", {
        "plan_id": provider_plan_id,
        "custom_id": f"{user.id}:{plan.code}:{tx.id}",
        "subscriber": {"email_address": user.email},
        "application_context": {"brand_name":"MarketAI", "locale":"pt-BR", "user_action":"SUBSCRIBE_NOW", "return_url":settings.public_app_url+"/assinatura?provider=paypal&success=1", "cancel_url":settings.public_app_url+"/assinatura?provider=paypal&canceled=1"}
    })
    tx.provider_object_id = str(data.get("id") or ""); tx.status = str(data.get("status") or "APPROVAL_PENDING").lower()
    approve = next((x.get("href") for x in data.get("links", []) if x.get("rel") in {"approve","payer-action"}), "")
    tx.checkout_url = approve or ""
    db.commit()
    return {"provider":"paypal", "payment_method":"paypal", "billing_id":tx.id, "subscription_id":tx.provider_object_id, "checkout_url":approve, "status":tx.status, "currency":currency, "amount":amount}


async def fetch_paypal_subscription(subscription_id: str):
    return await _paypal_request("GET", f"/v1/billing/subscriptions/{subscription_id}")


def sync_paypal_subscription(db: Session, data: dict):
    sid = str(data.get("id") or ""); custom = str(data.get("custom_id") or ""); sub = db.query(Subscription).filter_by(provider="paypal", provider_subscription_id=sid).first()
    user = None; plan_code = ""
    if custom:
        bits = custom.split(":")
        if len(bits) >= 2: user = db.get(User, bits[0]); plan_code = bits[1]
    if not sub and user:
        sub = _sub_for_user(db, user, plan_code or "essencial", "paypal"); sub.provider_subscription_id = sid
    if not sub: return None
    status = str(data.get("status") or "").upper()
    sub.status = {"ACTIVE":"active", "APPROVAL_PENDING":"pending", "APPROVED":"pending", "SUSPENDED":"past_due", "CANCELLED":"canceled", "EXPIRED":"canceled"}.get(status, status.lower() or "pending")
    next_time = (((data.get("billing_info") or {}).get("next_billing_time")) or "")
    if next_time:
        try: sub.current_period_end = datetime.fromisoformat(next_time.replace("Z", "+00:00"))
        except Exception: pass
    elif sub.status == "active": sub.current_period_end = utcnow() + timedelta(days=35)
    if sub.status == "active" and custom:
        bits = custom.split(":")
        if len(bits) >= 3:
            tx = db.get(BillingTransaction, bits[2])
            if tx and tx.credited_at is None:
                tx.status = "active"; tx.credited_at = utcnow()
    db.commit(); return sub


async def cancel_paypal_subscription(subscription_id: str):
    token = await paypal_access_token()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(_paypal_base()+f"/v1/billing/subscriptions/{subscription_id}/cancel", headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"}, json={"reason":"Canceled by MarketAI customer"})
    if r.status_code not in {200, 204}: raise RuntimeError(f"paypal_cancel_error:{r.status_code}:{r.text[:200]}")
    return {"id":subscription_id,"status":"CANCELLED"}


async def verify_paypal_webhook(headers, body: dict) -> bool:
    if not settings.paypal_webhook_id: return settings.allow_unverified_webhooks
    try:
        data = await _paypal_request("POST", "/v1/notifications/verify-webhook-signature", {
            "auth_algo": headers.get("paypal-auth-algo"), "cert_url": headers.get("paypal-cert-url"),
            "transmission_id": headers.get("paypal-transmission-id"), "transmission_sig": headers.get("paypal-transmission-sig"),
            "transmission_time": headers.get("paypal-transmission-time"), "webhook_id": settings.paypal_webhook_id, "webhook_event": body,
        })
        return data.get("verification_status") == "SUCCESS"
    except Exception:
        return False


# ---------------- Generic orchestration ----------------
async def create_checkout(db: Session, user: User, plan: Plan, payment_method="mercadopago", country_code="BR", currency=""):
    method = (payment_method or "mercadopago").lower(); country = (country_code or "BR").upper(); currency = (currency or currency_for_country(country)).upper()
    if method == "pix":
        if country != "BR": raise RuntimeError("pix_available_only_for_brazil")
        return await create_pix_payment(db, user, plan)
    if method == "card":
        return await create_stripe_checkout(db, user, plan, currency)
    if method == "paypal":
        return await create_paypal_subscription(db, user, plan, currency)
    if method == "mercadopago":
        if country != "BR": raise RuntimeError("mercadopago_subscription_configured_for_brazil_only")
        return await create_mp_subscription(db, user, plan)
    raise RuntimeError("unsupported_payment_method")


async def sync_user_subscription(db: Session, user: User):
    # First reconcile recent checkout attempts. This lets the desktop's "Atualizar"
    # recover even when a webhook was delayed.
    pending = db.query(BillingTransaction).filter_by(user_id=user.id).order_by(BillingTransaction.created_at.desc()).limit(8).all()
    for tx in pending:
        if not tx.provider_object_id or tx.status in {"failed","canceled","cancelled"}: continue
        try:
            if tx.payment_method == "pix":
                result = sync_pix_payment(db, await fetch_mp_payment(tx.provider_object_id))
                if result and result.status == "approved": return user.subscription
            elif tx.provider == "mercadopago" and tx.payment_method == "mercadopago":
                data = await fetch_mp_preapproval(tx.provider_object_id); sync_mp_subscription(db, data)
                tx.status = str(data.get("status") or tx.status); db.commit()
            elif tx.provider == "paypal":
                data = await fetch_paypal_subscription(tx.provider_object_id); sync_paypal_subscription(db, data)
                tx.status = str(data.get("status") or tx.status).lower(); db.commit()
            elif tx.provider == "stripe":
                sess = await fetch_stripe_checkout_session(tx.provider_object_id)
                sid = str(sess.get("subscription") or "")
                tx.status = str(sess.get("status") or tx.status); db.commit()
                if sid: sync_stripe_subscription(db, await fetch_stripe_subscription(sid))
        except Exception:
            pass

    sub = user.subscription
    if not sub or not sub.provider_subscription_id: return sub
    try:
        if sub.provider == "mercadopago": return sync_mp_subscription(db, await fetch_mp_preapproval(sub.provider_subscription_id))
        if sub.provider == "stripe": return sync_stripe_subscription(db, await fetch_stripe_subscription(sub.provider_subscription_id))
        if sub.provider == "paypal": return sync_paypal_subscription(db, await fetch_paypal_subscription(sub.provider_subscription_id))
        if sub.provider == "pix": return sync_pix_payment(db, await fetch_mp_payment(sub.provider_subscription_id))
    except Exception:
        return sub
    return sub


async def cancel_subscription(db: Session, user: User):
    sub = user.subscription
    if not sub or not sub.provider_subscription_id: raise RuntimeError("no_recurring_subscription")
    if sub.provider == "mercadopago":
        data = await cancel_mp_subscription(sub.provider_subscription_id); return sync_mp_subscription(db, data)
    if sub.provider == "stripe":
        data = await cancel_stripe_subscription(sub.provider_subscription_id); return sync_stripe_subscription(db, data)
    if sub.provider == "paypal":
        await cancel_paypal_subscription(sub.provider_subscription_id); sub.status = "canceled"; db.commit(); return sub
    if sub.provider == "pix": raise RuntimeError("pix_has_no_automatic_renewal")
    raise RuntimeError("subscription_provider_not_cancelable")


def verify_mp_signature(signature: str, request_id: str, data_id: str) -> bool:
    secret = settings.mercado_pago_webhook_secret
    if not secret: return settings.allow_unverified_webhooks
    vals = {}
    for p in (signature or "").split(","):
        if "=" in p:
            k, v = p.split("=", 1); vals[k.strip()] = v.strip()
    ts, v1 = vals.get("ts"), vals.get("v1")
    if not (ts and v1): return False
    pieces = []
    if data_id: pieces.append(f"id:{data_id.lower()};")
    if request_id: pieces.append(f"request-id:{request_id};")
    if ts: pieces.append(f"ts:{ts};")
    expected = hmac.new(secret.encode(), "".join(pieces).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)
