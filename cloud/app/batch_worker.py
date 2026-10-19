"""One bounded analysis at a time per API instance, with durable claims and recovery."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta

from sqlalchemy.exc import SQLAlchemyError

from app.batches import finalize_batch, now
from app.db import SessionLocal
from app.entitlements import consume_analysis
from app.evidence import recommendation_evidence
from app.history import record_analysis
from app.market_engine import run_analysis
from app.models import AnalysisBatch, AnalysisBatchItem, AnalysisHistory, User

logger = logging.getLogger(__name__)
ANALYSIS_TIMEOUT = 90
LEASE_SECONDS = 180


def summary_for(result):
    pricing = result.get('pricing') or {}
    market = result.get('market') or {}
    rec = (pricing.get('strategies') or {}).get('recommended') or {} if market.get('reliable') else {}
    return {'quality': (market.get('quality') or {}).get('state', 'unavailable'),
            'recommended_price': rec.get('price'), 'net_profit': rec.get('net_profit'),
            'net_margin_percent': rec.get('net_margin_percent'),
            'cost_floor': (pricing.get('costs') or {}).get('minimum_for_target_margin'),
            'collected_at': market.get('checked_at')}


def claim_next():
    with SessionLocal() as db:
        stale = db.query(AnalysisBatchItem).filter(AnalysisBatchItem.status == 'running',
                                                  AnalysisBatchItem.started_at < now() - timedelta(seconds=LEASE_SECONDS)).all()
        for item in stale:
            batch = db.get(AnalysisBatch, item.batch_id)
            item.status = 'cancelled' if batch.status == 'cancelling' else 'queued'
            item.started_at = None
            db.flush()
            finalize_batch(db, batch)
        db.commit()
        candidate = db.query(AnalysisBatchItem).join(AnalysisBatch).filter(
            AnalysisBatchItem.status == 'queued', AnalysisBatch.status == 'queued').order_by(
                AnalysisBatch.updated_at, AnalysisBatchItem.line, AnalysisBatchItem.id).first()
        if not candidate:
            return None
        item_id = candidate.id
        started = now()
        won = db.query(AnalysisBatchItem).filter_by(id=item_id, status='queued').update(
            {'status': 'running', 'started_at': started}, synchronize_session=False)
        if not won:
            db.rollback()
            return None
        batch = db.get(AnalysisBatch, candidate.batch_id)
        batch.status = 'running'
        batch.updated_at = started
        db.commit()
        return item_id


async def process_one():
    item_id = claim_next()
    if item_id is None:
        return False
    try:
        with SessionLocal() as db:
            item = db.get(AnalysisBatchItem, item_id)
            batch = db.get(AnalysisBatch, item.batch_id)
            user = db.get(User, batch.user_id)
            if not user or user.status != 'active' or user.deleted_at is not None:
                item.status, item.error_code = 'failed', 'account_unavailable'
                db.flush()
                finalize_batch(db, batch)
                db.commit()
                return True
            # An old worker might have stored history just before losing its claim.
            saved = db.query(AnalysisHistory).filter_by(user_id=user.id, client_id='batch:' + item.id).first()
            fields = json.loads(item.fields_json)
            result = json.loads(saved.payload_json) if saved and saved.payload_json else None
        if result is None:
            result = await asyncio.wait_for(run_analysis(fields), timeout=ANALYSIS_TIMEOUT)
        result['evidence'] = recommendation_evidence(result)
        with SessionLocal() as db:
            item = db.get(AnalysisBatchItem, item_id)
            if item.status != 'running':
                return True
            batch = db.get(AnalysisBatch, item.batch_id)
            user = db.get(User, batch.user_id)
            if user.status != 'active' or user.deleted_at is not None:
                item.status, item.error_code = 'failed', 'account_unavailable'
            else:
                previous = db.query(AnalysisHistory).filter_by(user_id=user.id, client_id='batch:' + item.id).first()
                item.analysis_id = record_analysis(db, user, result, client_id='batch:' + item.id, commit=False)
                if previous is None:
                    consume_analysis(db, user, commit=False)
                item.summary_json = json.dumps(summary_for(result), ensure_ascii=False, allow_nan=False)
                item.status = 'completed'
                item.error_code = ''
            db.flush()
            finalize_batch(db, batch)
            db.commit()
    except asyncio.CancelledError:
        with SessionLocal() as db:
            item = db.get(AnalysisBatchItem, item_id)
            if item and item.status == 'running':
                batch = db.get(AnalysisBatch, item.batch_id)
                item.status = 'cancelled' if batch.status == 'cancelling' else 'queued'
                item.started_at = None
                db.flush()
                finalize_batch(db, batch)
                db.commit()
        raise
    except Exception as exc:
        code = 'analysis_timeout' if isinstance(exc, TimeoutError) else 'analysis_failed'
        logger.error('Batch item %s failed (%s)', item_id, type(exc).__name__)
        with SessionLocal() as db:
            item = db.get(AnalysisBatchItem, item_id)
            if item and item.status == 'running':
                item.status, item.error_code = 'failed', code
                db.flush()
                finalize_batch(db, db.get(AnalysisBatch, item.batch_id))
                db.commit()
    return True


async def run_forever():
    while True:
        try:
            worked = await process_one()
        except SQLAlchemyError as exc:
            logger.error('Batch worker database error (%s)', type(exc).__name__)
            worked = False
        await asyncio.sleep(0.05 if worked else 1)
