"""Validated per-watch rules and shared, cooldown-controlled alert generation."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import AlertDetails, IntelligenceAlert, MarketSnapshot, ProductWatch, User, WatchAlertDelivery, WatchAlertRules

router = APIRouter(prefix='/v1/intelligence/watches', tags=['alert rules'])


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class AlertRules(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    price_enabled: bool = True
    price_change_percent: float = Field(default=8, gt=0, le=1000, allow_inf_nan=False)
    price_direction: Literal['both', 'drop', 'rise'] = 'both'
    margin_enabled: bool = True
    minimum_margin_percent: float = Field(default=15, ge=0, le=100, allow_inf_nan=False)
    stale_enabled: bool = False
    stale_after_hours: int = Field(default=24, ge=1, le=2160)
    cooldown_hours: int = Field(default=24, ge=1, le=720)


class RulesUpdate(BaseModel):
    revision: int = Field(ge=0)
    rules: AlertRules


def rules_for(db, watch):
    stored = db.get(WatchAlertRules, watch.id)
    if stored:
        return AlertRules.model_validate_json(stored.settings_json), stored.revision
    try:
        margin = float(json.loads(watch.settings_json or '{}').get('minimum_margin_percent', 15))
        return AlertRules(minimum_margin_percent=margin), 0
    except (ValueError, TypeError):
        return AlertRules(), 0


def owned_watch(db, user, watch_id):
    watch = db.query(ProductWatch).filter_by(id=watch_id, user_id=user.id).first()
    if not watch:
        raise HTTPException(404, 'watch_not_found')
    return watch


@router.get('/{watch_id}/alert-rules')
def get_rules(watch_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    watch = owned_watch(db, user, watch_id)
    rules, revision = rules_for(db, watch)
    return {'watch_id': watch.id, 'product_name': watch.product_name, 'revision': revision, 'rules': rules.model_dump()}


def store_rules(db, watch, rules, revision):
    if revision == 0:
        db.add(WatchAlertRules(watch_id=watch.id, settings_json=rules.model_dump_json(), revision=1))
        db.flush()
    elif not db.query(WatchAlertRules).filter_by(watch_id=watch.id, revision=revision).update(
            {'settings_json': rules.model_dump_json(), 'revision': revision+1, 'updated_at': now()}, synchronize_session=False):
        raise HTTPException(409, 'alert_rules_conflict')


@router.put('/{watch_id}/alert-rules')
def update_rules(watch_id: str, payload: RulesUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    watch = owned_watch(db, user, watch_id)
    try:
        store_rules(db, watch, payload.rules, payload.revision)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'alert_rules_conflict') from None
    return get_rules(watch_id, user, db)


def emit(db, watch, rules, kind, severity, title, message, details, at):
    """An atomic timestamp claim bounds each kind, including concurrent manual checks."""
    delivery = db.query(WatchAlertDelivery).filter_by(watch_id=watch.id, kind=kind).first()
    if not delivery:
        try:
            with db.begin_nested():
                db.add(WatchAlertDelivery(watch_id=watch.id, kind=kind))
                db.flush()
        except IntegrityError:
            pass
    cutoff = at - timedelta(hours=rules.cooldown_hours)
    won = db.query(WatchAlertDelivery).filter_by(watch_id=watch.id, kind=kind).filter(
        or_(WatchAlertDelivery.last_sent.is_(None), WatchAlertDelivery.last_sent <= cutoff)).update(
        {'last_sent': at}, synchronize_session=False)
    if not won:
        return False
    alert = IntelligenceAlert(user_id=watch.user_id, watch_id=watch.id, kind=kind, severity=severity,
                              title=title, message=message, created_at=at)
    db.add(alert)
    db.flush()
    db.add(AlertDetails(alert_id=alert.id, payload_json=json.dumps(
        {'product_name': watch.product_name, **details}, allow_nan=False)))
    return True


def latest_valid(db, watch):
    return db.query(MarketSnapshot).filter(MarketSnapshot.watch_id == watch.id,
        MarketSnapshot.user_id == watch.user_id, MarketSnapshot.market_median > 0,
        MarketSnapshot.listing_count >= 3).order_by(MarketSnapshot.created_at.desc()).first()


def check_staleness(db, watch, *, at=None, rules=None):
    if not watch.active:
        return False
    at = at or now()
    rules = rules or rules_for(db, watch)[0]
    if not rules.stale_enabled:
        return False
    previous = latest_valid(db, watch)
    baseline = aware(previous.created_at if previous else watch.created_at)
    hours = max(0, (at-baseline).total_seconds()/3600)
    if hours < rules.stale_after_hours:
        return False
    return emit(db, watch, rules, 'stale_data', 'attention', 'Sem coleta válida recente',
        f'{watch.product_name}: sem coleta válida há {hours:.1f} horas.',
        {'hours': round(hours, 1), 'threshold': rules.stale_after_hours,
         'last_valid_at': baseline.isoformat(), 'never_collected': previous is None}, at)


def evaluate(db, watch, analysis, snapshot, *, at=None):
    at = at or now()
    rules, _ = rules_for(db, watch)
    if not watch.active:
        return
    market = analysis.get('market') or {}
    if not market.get('reliable') or snapshot.market_median is None:
        check_staleness(db, watch, at=at, rules=rules)
        return
    previous = latest_valid(db, watch)  # Called before adding the new snapshot.
    if rules.price_enabled and previous and previous.market_median:
        pct = (snapshot.market_median-previous.market_median)/previous.market_median*100
        direction = 'rise' if pct > 0 else 'drop'
        if abs(pct) >= rules.price_change_percent and rules.price_direction in {'both', direction}:
            emit(db, watch, rules, 'price_move', 'opportunity' if pct > 0 else 'attention',
                 f"Preço de mercado {'subiu' if pct > 0 else 'caiu'} {abs(pct):.1f}%",
                 f'{watch.product_name}: R$ {previous.market_median:.2f} → R$ {snapshot.market_median:.2f}.',
                 {'change_percent': round(pct, 2), 'previous_median': previous.market_median,
                  'median': snapshot.market_median, 'collected_at': aware(snapshot.created_at).isoformat()}, at)
    if rules.margin_enabled and snapshot.net_margin is not None and snapshot.net_margin < rules.minimum_margin_percent:
        emit(db, watch, rules, 'margin', 'critical', 'Margem abaixo do limite',
             f'{watch.product_name}: margem líquida estimada em {snapshot.net_margin:.1f}%.',
             {'margin_percent': snapshot.net_margin, 'threshold': rules.minimum_margin_percent,
              'collected_at': aware(snapshot.created_at).isoformat()}, at)
