from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import User, Plan, Subscription, UsageCounter, Device
from app.config import settings

def utcnow(): return datetime.now(timezone.utc)
def period_key(): return utcnow().strftime("%Y-%m")
def _aware(dt):
    if dt is None: return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def entitlement(db:Session,user:User):
    sub=user.subscription
    if not sub:
        return {"active":False,"reason":"no_subscription"}
    plan=db.get(Plan,sub.plan_code)
    now=utcnow()
    trialing=sub.status=="trialing" and _aware(sub.trial_end) and _aware(sub.trial_end)>now
    paid=sub.status=="active" and (sub.current_period_end is None or _aware(sub.current_period_end)>now)
    active=bool(trialing or paid)
    quota=settings.trial_analyses if trialing else (plan.analyses_per_month if plan else 0)
    devices=1 if trialing else (plan.device_limit if plan else 1)
    row=db.query(UsageCounter).filter_by(user_id=user.id,period_key=period_key()).first()
    used=row.analyses_used if row else 0
    return {"active":active,"status":sub.status,"trialing":bool(trialing),"plan_code":sub.plan_code,"plan_name":plan.name if plan else sub.plan_code,"provider":sub.provider,"auto_renew":sub.provider in {"mercadopago","stripe","paypal"} and sub.status in {"active","pending","past_due"},"quota":quota,"used":used,"remaining":max(0,quota-used),"device_limit":devices,"trial_end":sub.trial_end.isoformat() if sub.trial_end else None,"current_period_end":sub.current_period_end.isoformat() if sub.current_period_end else None}

def consume_analysis(db:Session,user:User):
    ent=entitlement(db,user)
    if not ent["active"]: raise PermissionError("subscription_inactive")
    if ent["remaining"]<=0: raise PermissionError("quota_exhausted")
    key=period_key(); row=db.query(UsageCounter).filter_by(user_id=user.id,period_key=key).first()
    if not row:
        row=UsageCounter(user_id=user.id,period_key=key,analyses_used=0); db.add(row)
    row.analyses_used+=1; db.commit()
    return entitlement(db,user)
