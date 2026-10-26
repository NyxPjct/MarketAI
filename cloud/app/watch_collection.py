"""Snapshot persistence shared by the Sentinel and manual collection routes."""
import json

from app.alert_rules import evaluate, rules_for, emit, check_staleness, now
from app.copilot import analysis_context
from app.intelligence_engine import data_quality_score, market_score, autopilot_price
from app.models import MarketSnapshot


def persist_snapshot(db, watch, analysis, fields):
    at = now()
    quality, score = data_quality_score(analysis), market_score(analysis)
    rules, _ = rules_for(db, watch)
    autopilot = autopilot_price(analysis, str(fields.get('autopilot_strategy') or 'balanced'),
        float(fields.get('undercut_amount') or 1), rules.minimum_margin_percent) if watch.autopilot_enabled else {'available': False}
    reliable = (analysis.get('market') or {}).get('reliable', False)
    pricing = analysis.get('pricing') or {}
    market = (pricing.get('market') or {}) if reliable else {}
    rec = ((pricing.get('strategies') or {}).get('recommended') or {}) if reliable else {}
    snapshot = MarketSnapshot(watch_id=watch.id, user_id=watch.user_id,
        market_median=market.get('median'), market_min=market.get('min'), market_max=market.get('max'),
        listing_count=int(market.get('count') or 0), quality_score=quality['score'], market_score=score.get('score'),
        net_margin=rec.get('net_margin_percent'), suggested_price=autopilot.get('suggested_price') if autopilot.get('available') else rec.get('price'),
        payload_json=json.dumps({'quality': quality, 'score': score, 'autopilot': autopilot,
                                 'analysis': analysis_context(analysis)}, ensure_ascii=False), created_at=at)
    evaluate(db, watch, analysis, snapshot, at=at)
    db.add(snapshot)
    watch.updated_at = at
    return {'snapshot': snapshot, 'data_quality': quality, 'market_score': score, 'autopilot': autopilot}


def record_failure(db, watch):
    at = now()
    if watch.active:
        rules, _ = rules_for(db, watch)
        if rules.price_enabled or rules.margin_enabled or rules.stale_enabled:
            emit(db, watch, rules, 'source_error', 'info', 'Não foi possível verificar o produto',
                 f'{watch.product_name}: tente uma nova coleta.', {}, at)
        check_staleness(db, watch, at=at, rules=rules)
    watch.updated_at = at
