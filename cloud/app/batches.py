"""Durable, account-scoped catalog analysis jobs."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.batch_csv import BatchCreate, CSVInputError, MAX_CSV_BYTES, preview_csv
from app.db import get_db
from app.deps import current_user
from app.models import AnalysisBatch, AnalysisBatchItem, Device, User

router = APIRouter(prefix='/v1/batches', tags=['batches'])
FINAL_STATES = {'completed', 'completed_with_errors', 'cancelled'}


def now():
    return datetime.now(timezone.utc)


def iso(value):
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def batch_for_user(db, user, batch_id):
    batch = db.query(AnalysisBatch).filter_by(id=batch_id, user_id=user.id).first()
    if not batch:
        raise HTTPException(404, 'batch_not_found')
    return batch


def batch_json(db, batch, include_rows=True):
    items = db.query(AnalysisBatchItem).filter_by(batch_id=batch.id).order_by(AnalysisBatchItem.line, AnalysisBatchItem.id).all()
    counts = {state: sum(item.status == state for item in items)
              for state in ('queued', 'running', 'completed', 'failed', 'cancelled')}
    result = {'id': batch.id, 'status': batch.status, 'counts': counts, 'total': len(items),
              'created_at': iso(batch.created_at), 'updated_at': iso(batch.updated_at)}
    if include_rows:
        result['rows'] = [{'id': item.id, 'line': item.line, 'fields': json.loads(item.fields_json),
                           'status': item.status, 'analysis_id': item.analysis_id,
                           'summary': json.loads(item.summary_json), 'error_code': item.error_code} for item in items]
    return result


def finalize_batch(db, batch):
    statuses = [status for status, in db.query(AnalysisBatchItem.status).filter_by(batch_id=batch.id).all()]
    if not any(s in {'queued', 'running'} for s in statuses):
        batch.status = 'cancelled' if batch.status == 'cancelling' else (
            'completed_with_errors' if 'failed' in statuses else 'completed')
        batch.active_owner = None
    elif batch.status != 'cancelling' and 'running' not in statuses:
        batch.status = 'queued'
    batch.updated_at = now()


@router.post('/preview')
async def preview(file: UploadFile = File(...), user: User = Depends(current_user)):
    content = await file.read(MAX_CSV_BYTES + 1)
    try:
        return preview_csv(content)
    except CSVInputError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get('')
def list_batches(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(AnalysisBatch).filter_by(user_id=user.id).order_by(AnalysisBatch.created_at.desc()).limit(20).all()
    return {'items': [batch_json(db, batch, False) for batch in rows]}


@router.post('')
def create_batch(payload: BatchCreate, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    device_uuid = request.headers.get('x-device-id', '').strip()
    if not db.query(Device).filter_by(user_id=user.id, device_uuid=device_uuid, active=True).first():
        raise HTTPException(403, 'device_not_authorized')
    key = str(payload.client_id)
    existing = db.query(AnalysisBatch).filter_by(user_id=user.id, client_id=key).first()
    if existing:
        return batch_json(db, existing)
    batch = AnalysisBatch(user_id=user.id, client_id=key, active_owner=user.id)
    try:
        db.add(batch)
        db.flush()
        for row in payload.rows:
            db.add(AnalysisBatchItem(batch_id=batch.id, line=row.line,
                                    fields_json=json.dumps(row.fields.model_dump(), ensure_ascii=False)))
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(AnalysisBatch).filter_by(user_id=user.id, client_id=key).first()
        if existing:
            return batch_json(db, existing)
        if db.query(AnalysisBatch).filter_by(active_owner=user.id).first():
            raise HTTPException(409, 'batch_already_active') from None
        raise
    db.refresh(batch)
    return batch_json(db, batch)


@router.get('/{batch_id}')
def get_batch(batch_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return batch_json(db, batch_for_user(db, user, batch_id))


@router.post('/{batch_id}/cancel')
def cancel_batch(batch_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    batch = batch_for_user(db, user, batch_id)
    if batch.status not in FINAL_STATES:
        batch.status = 'cancelling'
        db.query(AnalysisBatchItem).filter_by(batch_id=batch.id, status='queued').update(
            {'status': 'cancelled'}, synchronize_session=False)
        finalize_batch(db, batch)
        db.commit()
    return batch_json(db, batch)


def spreadsheet_cell(value):
    # Preserve numeric values while preventing formulas in imported product text.
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


@router.get('/{batch_id}/export')
def export_batch(batch_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    batch = batch_json(db, batch_for_user(db, user, batch_id))
    output = io.StringIO(newline='')
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['line', 'sku', 'product_name', 'variant_text', 'status', 'quality', 'recommended_price_brl',
                     'net_profit_brl', 'net_margin_percent', 'cost_floor_brl', 'collected_at', 'error', 'analysis_id'])
    for row in batch['rows']:
        summary = row['summary']
        values = [row['line'], row['fields'].get('sku', ''), row['fields']['product_name'], row['fields']['variant_text'], row['status'],
                  summary.get('quality'), summary.get('recommended_price'), summary.get('net_profit'),
                  summary.get('net_margin_percent'), summary.get('cost_floor'), summary.get('collected_at'),
                  row['error_code'], row['analysis_id']]
        writer.writerow([spreadsheet_cell(value) for value in values])
    return Response(content=output.getvalue().encode('utf-8-sig'), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="MarketAI-batch-{batch_id}.csv"'})


@router.delete('/{batch_id}')
def delete_batch(batch_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    batch = batch_for_user(db, user, batch_id)
    if batch.status not in FINAL_STATES:
        raise HTTPException(409, 'batch_still_active')
    db.query(AnalysisBatchItem).filter_by(batch_id=batch.id).delete(synchronize_session=False)
    db.delete(batch)
    db.commit()
    return {'ok': True}
