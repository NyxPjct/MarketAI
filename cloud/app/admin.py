from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import current_admin
from app.entitlements import entitlement
from app.models import (
    AuditEvent,
    BillingTransaction,
    Device,
    License,
    LicenseRedemption,
    Plan,
    RefreshSession,
    Subscription,
    UsageCounter,
    User,
)
from app.security import create_access_token, generate_license_code, license_hash, verify_password

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def utcnow():
    return datetime.now(timezone.utc)


def aware(dt):
    return dt if (dt is None or dt.tzinfo) else dt.replace(tzinfo=timezone.utc)


def iso(dt):
    return aware(dt).isoformat() if dt else None


def audit(db: Session, admin: User, event: str, detail: str = "", target_user_id: str | None = None):
    suffix = f" target_user={target_user_id}" if target_user_id else ""
    db.add(AuditEvent(user_id=admin.id, event=f"admin.{event}", detail=(detail + suffix).strip()))


def user_summary(db: Session, user: User) -> dict[str, Any]:
    sub = user.subscription
    ent = entitlement(db, user) if sub else {
        "active": False,
        "plan_code": None,
        "plan_name": None,
        "remaining": 0,
        "quota": 0,
        "device_limit": 0,
    }
    active_devices = db.query(Device).filter_by(user_id=user.id, active=True).count()
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "status": user.status,
        "created_at": iso(user.created_at),
        "email_verified": user.email_verified,
        "subscription": {
            "plan_code": sub.plan_code if sub else None,
            "status": sub.status if sub else None,
            "provider": sub.provider if sub else None,
            "period_end": iso(sub.current_period_end) if sub else None,
            "trial_end": iso(sub.trial_end) if sub else None,
        },
        "entitlement": ent,
        "active_devices": active_devices,
    }


@router.post("/auth/login")
def admin_login(payload: dict = Body(...), db: Session = Depends(get_db)):
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    user = db.query(User).filter_by(email=email).first()
    if not user or user.role != "admin" or not verify_password(password, user.password_hash):
        raise HTTPException(401, "invalid_admin_credentials")
    if user.status != "active" or user.deleted_at is not None:
        raise HTTPException(403, "admin_account_inactive")
    token = create_access_token(user.id, "admin")
    db.add(AuditEvent(user_id=user.id, event="admin.login", detail="admin_panel"))
    db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.access_minutes * 60,
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role},
    }


@router.get("/me")
def admin_me(admin: User = Depends(current_admin)):
    return {"id": admin.id, "email": admin.email, "full_name": admin.full_name, "role": admin.role}


@router.get("/dashboard")
def dashboard(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    now = utcnow()
    since = now - timedelta(days=30)
    period_key = now.strftime("%Y-%m")

    total_users = db.query(User).filter(User.role != "admin", User.deleted_at.is_(None)).count()
    active_users = db.query(User).filter(User.role != "admin", User.status == "active", User.deleted_at.is_(None)).count()
    blocked_users = db.query(User).filter(User.role != "admin", User.status != "active", User.deleted_at.is_(None)).count()
    new_users = db.query(User).filter(User.role != "admin", User.created_at >= since, User.deleted_at.is_(None)).count()

    active_subs = db.query(Subscription).filter(Subscription.status.in_(["active", "trialing"])).count()
    trials = db.query(Subscription).filter(Subscription.status == "trialing").count()
    past_due = db.query(Subscription).filter(Subscription.status == "past_due").count()
    active_devices = db.query(Device).filter_by(active=True).count()
    analyses_month = db.query(func.coalesce(func.sum(UsageCounter.analyses_used), 0)).filter(UsageCounter.period_key == period_key).scalar() or 0

    plan_rows = db.query(Subscription.plan_code, func.count(Subscription.id)).group_by(Subscription.plan_code).all()
    provider_rows = db.query(Subscription.provider, func.count(Subscription.id)).group_by(Subscription.provider).all()
    payment_provider_rows = db.query(BillingTransaction.provider, func.count(BillingTransaction.id)).filter(BillingTransaction.created_at >= since).group_by(BillingTransaction.provider).all()

    confirmed = db.query(BillingTransaction).filter(BillingTransaction.credited_at.is_not(None), BillingTransaction.credited_at >= since).all()
    revenue: dict[str, float] = {}
    for tx in confirmed:
        revenue[tx.currency] = round(revenue.get(tx.currency, 0.0) + float(tx.amount or 0), 2)

    recent_users = db.query(User).filter(User.role != "admin").order_by(User.created_at.desc()).limit(6).all()
    recent_payments = db.query(BillingTransaction).order_by(BillingTransaction.created_at.desc()).limit(8).all()

    return {
        "generated_at": iso(now),
        "metrics": {
            "users": total_users,
            "active_users": active_users,
            "blocked_users": blocked_users,
            "new_users_30d": new_users,
            "active_subscriptions": active_subs,
            "trials": trials,
            "past_due": past_due,
            "active_devices": active_devices,
            "analyses_this_month": int(analyses_month),
            "confirmed_revenue_30d": revenue,
        },
        "plans": [{"plan": k or "sem plano", "count": v} for k, v in plan_rows],
        "subscription_providers": [{"provider": k or "-", "count": v} for k, v in provider_rows],
        "payment_providers_30d": [{"provider": k or "-", "count": v} for k, v in payment_provider_rows],
        "recent_users": [user_summary(db, u) for u in recent_users],
        "recent_payments": [payment_payload(tx) for tx in recent_payments],
    }


def payment_payload(tx: BillingTransaction) -> dict[str, Any]:
    return {
        "id": tx.id,
        "user_id": tx.user_id,
        "plan_code": tx.plan_code,
        "provider": tx.provider,
        "payment_method": tx.payment_method,
        "provider_object_id": tx.provider_object_id,
        "status": tx.status,
        "amount": tx.amount,
        "currency": tx.currency,
        "credited_at": iso(tx.credited_at),
        "created_at": iso(tx.created_at),
        "updated_at": iso(tx.updated_at),
    }


@router.get("/users")
def users(
    q: str = "",
    status: str = "",
    plan: str = "",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(User).filter(User.role != "admin", User.deleted_at.is_(None))
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(User.email.ilike(like), User.full_name.ilike(like), User.id.ilike(like)))
    if status.strip():
        query = query.filter(User.status == status.strip())
    if plan.strip():
        query = query.join(Subscription, Subscription.user_id == User.id).filter(Subscription.plan_code == plan.strip())
    total = query.count()
    rows = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [user_summary(db, u) for u in rows], "limit": limit, "offset": offset}


@router.get("/users/{user_id}")
def user_detail(user_id: str, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user or user.deleted_at is not None:
        raise HTTPException(404, "user_not_found")
    devices = db.query(Device).filter_by(user_id=user.id).order_by(Device.last_seen.desc()).all()
    usage = db.query(UsageCounter).filter_by(user_id=user.id).order_by(UsageCounter.period_key.desc()).limit(12).all()
    payments = db.query(BillingTransaction).filter_by(user_id=user.id).order_by(BillingTransaction.created_at.desc()).limit(30).all()
    events = db.query(AuditEvent).filter_by(user_id=user.id).order_by(AuditEvent.created_at.desc()).limit(30).all()
    data = user_summary(db, user)
    data.update({
        "devices": [{"id": d.id, "name": d.name, "device_uuid": d.device_uuid, "active": d.active, "first_seen": iso(d.first_seen), "last_seen": iso(d.last_seen)} for d in devices],
        "usage": [{"period_key": u.period_key, "analyses_used": u.analyses_used, "updated_at": iso(u.updated_at)} for u in usage],
        "payments": [payment_payload(p) for p in payments],
        "audit": [{"id": e.id, "event": e.event, "detail": e.detail, "created_at": iso(e.created_at)} for e in events],
    })
    return data


@router.patch("/users/{user_id}/status")
def update_user_status(user_id: str, payload: dict = Body(...), admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user or user.role == "admin":
        raise HTTPException(404, "user_not_found")
    status = str(payload.get("status") or "").strip().lower()
    if status not in {"active", "blocked", "suspended"}:
        raise HTTPException(400, "invalid_status")
    old = user.status
    user.status = status
    if status != "active":
        for session in db.query(RefreshSession).filter_by(user_id=user.id, revoked=False).all():
            session.revoked = True
    audit(db, admin, "user_status", f"{old}->{status}", user.id)
    db.commit()
    return user_summary(db, user)


@router.patch("/users/{user_id}/subscription")
def update_subscription(user_id: str, payload: dict = Body(...), admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user or user.role == "admin":
        raise HTTPException(404, "user_not_found")
    plan_code = str(payload.get("plan_code") or "").strip()
    plan = db.get(Plan, plan_code)
    if not plan:
        raise HTTPException(404, "plan_not_found")
    status = str(payload.get("status") or "active").strip()
    if status not in {"active", "trialing", "past_due", "canceled", "pending"}:
        raise HTTPException(400, "invalid_subscription_status")
    days = max(0, min(3650, int(payload.get("days") or 0)))
    sub = user.subscription
    if sub and sub.provider in {"mercadopago", "stripe", "paypal"} and sub.status in {"active", "trialing", "past_due"}:
        raise HTTPException(409, "cancel_recurring_subscription_at_gateway_before_manual_override")
    if not sub:
        sub = Subscription(user_id=user.id)
        db.add(sub)
    old = f"{sub.plan_code}/{sub.status}/{sub.provider}"
    sub.plan_code = plan_code
    sub.status = status
    sub.provider = "admin"
    sub.provider_subscription_id = None
    if status == "trialing":
        sub.trial_end = utcnow() + timedelta(days=days or settings.trial_days)
    elif days:
        base = max(utcnow(), aware(sub.current_period_end) or utcnow())
        sub.current_period_end = base + timedelta(days=days)
        sub.trial_end = None
    elif status == "active" and not sub.current_period_end:
        sub.current_period_end = utcnow() + timedelta(days=30)
    audit(db, admin, "subscription_override", f"{old}->{plan_code}/{status}/admin days={days}", user.id)
    db.commit()
    return user_summary(db, user)


@router.post("/users/{user_id}/reset-usage")
def reset_usage(user_id: str, payload: dict = Body(default={}), admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "user_not_found")
    period = str(payload.get("period_key") or utcnow().strftime("%Y-%m"))
    row = db.query(UsageCounter).filter_by(user_id=user.id, period_key=period).first()
    if row:
        row.analyses_used = 0
    audit(db, admin, "usage_reset", f"period={period}", user.id)
    db.commit()
    return {"ok": True, "period_key": period}


@router.get("/subscriptions")
def subscriptions(
    status: str = "", provider: str = "", limit: int = Query(100, ge=1, le=300), offset: int = Query(0, ge=0),
    admin: User = Depends(current_admin), db: Session = Depends(get_db),
):
    q = db.query(Subscription)
    if status: q = q.filter(Subscription.status == status)
    if provider: q = q.filter(Subscription.provider == provider)
    total = q.count()
    rows = q.order_by(Subscription.updated_at.desc()).offset(offset).limit(limit).all()
    items = []
    for s in rows:
        u = db.get(User, s.user_id)
        items.append({"id": s.id, "user_id": s.user_id, "email": u.email if u else "", "full_name": u.full_name if u else "", "plan_code": s.plan_code, "status": s.status, "provider": s.provider, "provider_subscription_id": s.provider_subscription_id, "trial_end": iso(s.trial_end), "current_period_end": iso(s.current_period_end), "updated_at": iso(s.updated_at)})
    return {"total": total, "items": items}


@router.get("/payments")
def payments(
    provider: str = "", status: str = "", currency: str = "", limit: int = Query(100, ge=1, le=300), offset: int = Query(0, ge=0),
    admin: User = Depends(current_admin), db: Session = Depends(get_db),
):
    q = db.query(BillingTransaction)
    if provider: q = q.filter(BillingTransaction.provider == provider)
    if status: q = q.filter(BillingTransaction.status == status)
    if currency: q = q.filter(BillingTransaction.currency == currency.upper())
    total = q.count()
    rows = q.order_by(BillingTransaction.created_at.desc()).offset(offset).limit(limit).all()
    items = []
    for tx in rows:
        u = db.get(User, tx.user_id)
        item = payment_payload(tx)
        item["email"] = u.email if u else ""
        item["full_name"] = u.full_name if u else ""
        items.append(item)
    return {"total": total, "items": items}


@router.get("/licenses")
def licenses(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    rows = db.query(License).order_by(License.created_at.desc()).limit(500).all()
    return {"items": [{"id": l.id, "code_hint": l.code_hint, "plan_code": l.plan_code, "duration_days": l.duration_days, "max_redemptions": l.max_redemptions, "redeemed_count": l.redeemed_count, "active": l.active, "created_at": iso(l.created_at)} for l in rows]}


@router.post("/licenses/create")
def create_license(payload: dict = Body(...), admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    plan_code = str(payload.get("plan_code") or "pro")
    if not db.get(Plan, plan_code):
        raise HTTPException(404, "plan_not_found")
    code = generate_license_code()
    lic = License(
        code_hash=license_hash(code), code_hint=code[-5:], plan_code=plan_code,
        duration_days=max(1, min(3650, int(payload.get("duration_days") or 30))),
        max_redemptions=max(1, min(10000, int(payload.get("max_redemptions") or 1))),
    )
    db.add(lic)
    audit(db, admin, "license_create", f"plan={plan_code} days={lic.duration_days} redemptions={lic.max_redemptions}")
    db.commit()
    return {"license_key": code, "id": lic.id, "plan_code": plan_code, "duration_days": lic.duration_days, "max_redemptions": lic.max_redemptions}


@router.patch("/licenses/{license_id}")
def update_license(license_id: str, payload: dict = Body(...), admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    lic = db.get(License, license_id)
    if not lic:
        raise HTTPException(404, "license_not_found")
    if "active" in payload:
        lic.active = bool(payload.get("active"))
    audit(db, admin, "license_update", f"license={lic.id} active={lic.active}")
    db.commit()
    return {"id": lic.id, "active": lic.active}


@router.get("/devices")
def devices(
    q: str = "", active: str = "", limit: int = Query(150, ge=1, le=500), offset: int = Query(0, ge=0),
    admin: User = Depends(current_admin), db: Session = Depends(get_db),
):
    query = db.query(Device)
    if active in {"true", "false"}: query = query.filter(Device.active == (active == "true"))
    if q:
        like = f"%{q}%"
        user_ids = [x[0] for x in db.query(User.id).filter(or_(User.email.ilike(like), User.full_name.ilike(like))).all()]
        query = query.filter(or_(Device.name.ilike(like), Device.device_uuid.ilike(like), Device.user_id.in_(user_ids or ["-"])))
    total = query.count()
    rows = query.order_by(Device.last_seen.desc()).offset(offset).limit(limit).all()
    items = []
    for d in rows:
        u = db.get(User, d.user_id)
        items.append({"id": d.id, "user_id": d.user_id, "email": u.email if u else "", "name": d.name, "device_uuid": d.device_uuid, "active": d.active, "first_seen": iso(d.first_seen), "last_seen": iso(d.last_seen)})
    return {"total": total, "items": items}


@router.patch("/devices/{device_id}")
def update_device(device_id: str, payload: dict = Body(...), admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    d = db.get(Device, device_id)
    if not d:
        raise HTTPException(404, "device_not_found")
    d.active = bool(payload.get("active"))
    audit(db, admin, "device_update", f"device={d.id} active={d.active}", d.user_id)
    db.commit()
    return {"id": d.id, "active": d.active}


@router.get("/usage")
def usage(period_key: str = "", limit: int = Query(200, ge=1, le=500), admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    period = period_key or utcnow().strftime("%Y-%m")
    rows = db.query(UsageCounter).filter_by(period_key=period).order_by(UsageCounter.analyses_used.desc()).limit(limit).all()
    items = []
    for r in rows:
        u = db.get(User, r.user_id)
        items.append({"user_id": r.user_id, "email": u.email if u else "", "period_key": r.period_key, "analyses_used": r.analyses_used, "updated_at": iso(r.updated_at)})
    return {"period_key": period, "items": items, "total_analyses": sum(x.analyses_used for x in rows)}


@router.get("/audit")
def audit_log(q: str = "", limit: int = Query(150, ge=1, le=500), offset: int = Query(0, ge=0), admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    query = db.query(AuditEvent)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(AuditEvent.event.ilike(like), AuditEvent.detail.ilike(like), AuditEvent.user_id.ilike(like)))
    total = query.count()
    rows = query.order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit).all()
    items = []
    for e in rows:
        u = db.get(User, e.user_id) if e.user_id else None
        items.append({"id": e.id, "user_id": e.user_id, "email": u.email if u else "", "event": e.event, "detail": e.detail, "created_at": iso(e.created_at)})
    return {"total": total, "items": items}


@router.get("/plans")
def admin_plans(admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    rows = db.query(Plan).order_by(Plan.price_brl).all()
    return {"items": [{"code": p.code, "name": p.name, "price_brl": p.price_brl, "analyses_per_month": p.analyses_per_month, "device_limit": p.device_limit, "active": p.active} for p in rows]}


@router.patch("/plans/{plan_code}")
def update_plan(plan_code: str, payload: dict = Body(...), admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    p = db.get(Plan, plan_code)
    if not p:
        raise HTTPException(404, "plan_not_found")
    old = f"name={p.name} price={p.price_brl} quota={p.analyses_per_month} devices={p.device_limit} active={p.active}"
    if "name" in payload: p.name = str(payload.get("name") or p.name)[:80]
    if "price_brl" in payload: p.price_brl = max(0, float(payload.get("price_brl") or 0))
    if "analyses_per_month" in payload: p.analyses_per_month = max(1, int(payload.get("analyses_per_month") or 1))
    if "device_limit" in payload: p.device_limit = max(1, int(payload.get("device_limit") or 1))
    if "active" in payload: p.active = bool(payload.get("active"))
    audit(db, admin, "plan_update", f"{plan_code}: {old} -> name={p.name} price={p.price_brl} quota={p.analyses_per_month} devices={p.device_limit} active={p.active}")
    db.commit()
    return {"code": p.code, "name": p.name, "price_brl": p.price_brl, "analyses_per_month": p.analyses_per_month, "device_limit": p.device_limit, "active": p.active}
