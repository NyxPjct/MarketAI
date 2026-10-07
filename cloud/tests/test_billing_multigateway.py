import os
os.environ.setdefault("DATABASE_URL","sqlite:///./test-marketai-cloud.db")
os.environ.setdefault("JWT_SECRET","test-secret-abcdefghijklmnopqrstuvwxyz-1234567890")
os.environ.setdefault("ADMIN_API_KEY","admin-test")
from datetime import datetime, timezone

from app.billing import payment_methods, plan_price, sync_pix_payment
from app.config import settings
from app.db import SessionLocal
from app.models import User, Plan, Subscription, BillingTransaction
from app.security import hash_password


def _set(name, value):
    object.__setattr__(settings, name, value)


def test_payment_method_matrix():
    old=(settings.mercado_pago_token,settings.stripe_secret_key,settings.paypal_client_id,settings.paypal_client_secret)
    try:
        _set("mercado_pago_token","mp-test"); _set("stripe_secret_key","sk_test"); _set("paypal_client_id","pp"); _set("paypal_client_secret","pps")
        br={m["id"] for m in payment_methods("BR")}
        us={m["id"] for m in payment_methods("US")}
        assert {"pix","card","paypal","mercadopago"}.issubset(br)
        assert "pix" not in us and "mercadopago" not in us
        assert {"card","paypal"}.issubset(us)
    finally:
        _set("mercado_pago_token",old[0]); _set("stripe_secret_key",old[1]); _set("paypal_client_id",old[2]); _set("paypal_client_secret",old[3])


def test_plan_prices_by_currency():
    db=SessionLocal()
    try:
        p=db.get(Plan,"pro")
        assert p is not None
        assert plan_price(p,"BRL") > 0
        assert plan_price(p,"USD") == 19.99
        assert plan_price(p,"EUR") == 18.99
        assert plan_price(p,"JPY") == 2990
    finally: db.close()


def test_pix_approval_grants_30_days():
    db=SessionLocal()
    try:
        user=User(email="pix-billing@example.com",password_hash=hash_password("SenhaForte123!"),full_name="Pix")
        db.add(user); db.flush()
        sub=Subscription(user_id=user.id,plan_code="essencial",status="pending",provider="trial")
        db.add(sub); db.flush()
        tx=BillingTransaction(user_id=user.id,plan_code="pro",provider="mercadopago",payment_method="pix",provider_object_id="998877",status="pending",amount=99.90,currency="BRL",period_days=30)
        db.add(tx); db.commit()
        before=datetime.now(timezone.utc)
        sync_pix_payment(db,{"id":"998877","status":"approved"})
        db.refresh(sub); db.refresh(tx)
        end=sub.current_period_end
        if end.tzinfo is None: end=end.replace(tzinfo=timezone.utc)
        assert sub.status=="active" and sub.plan_code=="pro" and sub.provider=="pix"
        assert (end-before).days >= 29
        assert tx.credited_at is not None
        # idempotent: the same webhook must not add another 30 days
        first=end
        sync_pix_payment(db,{"id":"998877","status":"approved"}); db.refresh(sub)
        second=sub.current_period_end
        if second.tzinfo is None: second=second.replace(tzinfo=timezone.utc)
        assert abs((second-first).total_seconds()) < 2
    finally:
        db.query(BillingTransaction).filter(BillingTransaction.user_id==user.id).delete()
        db.query(Subscription).filter(Subscription.user_id==user.id).delete()
        db.query(User).filter(User.id==user.id).delete(); db.commit(); db.close()
