from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models import User, UsageCounter


ALL_FEATURES = [
    "analysis",
    "profit",
    "sentinel",
    "radar",
    "forecast",
    "copilot",
    "autopilot",
    "api",
    "teams",
    "enterprise",
]


def utcnow():
    return datetime.now(timezone.utc)


def period_key():
    return utcnow().strftime("%Y-%m")


def entitlement(db: Session, user: User):
    """Open-source Community entitlement.

    MarketAI is free for every authenticated account. UsageCounter remains as
    telemetry for the user's own account, but it never blocks product analysis.
    """
    row = (
        db.query(UsageCounter)
        .filter_by(user_id=user.id, period_key=period_key())
        .first()
    )
    used = row.analyses_used if row else 0
    return {
        "active": True,
        "status": "active",
        "trialing": False,
        "plan_code": "community",
        "plan_name": "Community — Gratuito",
        "provider": "open_source",
        "auto_renew": False,
        "quota": None,
        "used": used,
        "remaining": None,
        "unlimited": True,
        "device_limit": 999999,
        "features": list(ALL_FEATURES),
        "watch_limit": None,
        "trial_end": None,
        "current_period_end": None,
        "open_source": True,
        "price": 0,
    }


def consume_analysis(db: Session, user: User):
    """Track usage without enforcing a paid quota."""
    key = period_key()
    row = (
        db.query(UsageCounter)
        .filter_by(user_id=user.id, period_key=key)
        .first()
    )
    if not row:
        row = UsageCounter(user_id=user.id, period_key=key, analyses_used=0)
        db.add(row)
    row.analyses_used += 1
    db.commit()
    return entitlement(db, user)
