"""Account-owned SKU catalog, versioned inputs and trusted analysis comparisons."""
from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analysis_summary import summary_for
from app.batch_csv import AnalysisFields, BatchCreate, BatchRow
from app.batches import batch_json, store_batch, require_device, iso, now
from app.db import get_db
from app.deps import current_user
from app.models import CatalogProduct, CatalogRevision, CatalogAnalysis, AnalysisHistory, ProductWatch, User

router = APIRouter(prefix='/v1/catalog', tags=['catalog'])


def sku_key(value):
    normalized = unicodedata.normalize('NFKC', value).strip().casefold()
    return hashlib.sha256(normalized.encode()).hexdigest()


def fingerprint(fields):
    # Stock and supplier names do not change the price calculation.
    values = AnalysisFields.model_validate(fields.model_dump()).model_dump(exclude={'sku', 'supplier_name'})
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


class CatalogFields(AnalysisFields):
    sku: str = Field(min_length=1, max_length=120)


class ProductInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fields: CatalogFields
    stock: int = Field(default=0, ge=0, le=1_000_000_000)


class ProductUpdate(ProductInput):
    revision: int = Field(ge=1)


class CatalogImport(BaseModel):
    products: list[ProductInput] = Field(min_length=1, max_length=50)


class ProductRef(BaseModel):
    id: UUID
    revision: int = Field(ge=1)


class Selection(BaseModel):
    products: list[ProductRef] = Field(min_length=1, max_length=50)


class AnalyzeSelection(Selection):
    client_id: UUID


def owned(db, user, product_id):
    product = db.query(CatalogProduct).filter_by(id=str(product_id), user_id=user.id).first()
    if not product:
        raise HTTPException(404, 'catalog_product_not_found')
    return product


def selected(db, user, payload):
    ids = [str(ref.id) for ref in payload.products]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, 'duplicate_catalog_selection')
    result = []
    for ref in payload.products:
        product = owned(db, user, ref.id)
        if product.revision != ref.revision:
            raise HTTPException(409, 'catalog_revision_conflict')
        result.append(product)
    return result


def product_json(db, product, analysis=None):
    watch = db.get(ProductWatch, product.watch_id) if product.watch_id else None
    return {'id': product.id, 'fields': json.loads(product.fields_json), 'stock': product.stock,
            'revision': product.revision, 'created_at': iso(product.created_at), 'updated_at': iso(product.updated_at),
            'watch_id': product.watch_id, 'monitoring': bool(watch and watch.active),
            'latest': {**json.loads(analysis.summary_json), 'analysis_id': analysis.history_id,
                       'outdated': analysis.fingerprint != product.fingerprint} if analysis else None}


def save_revision(db, product):
    db.add(CatalogRevision(product_id=product.id, revision=product.revision,
                           fields_json=product.fields_json, stock=product.stock))


def link_analysis(db, user, history, result):
    """Called only when recording a trusted result; client summaries cannot create links."""
    try:
        fields = AnalysisFields.model_validate(result.get('request') or {})
    except ValidationError:
        return
    if not fields.sku:
        return
    product = db.query(CatalogProduct).filter_by(user_id=user.id, sku_key=sku_key(fields.sku)).first()
    if not product:
        return
    summary = summary_for(result)
    db.add(CatalogAnalysis(history_id=history.id, product_id=product.id, fingerprint=fingerprint(fields),
                           summary_json=json.dumps(summary, allow_nan=False), quality=summary['quality'],
                           net_margin=summary['net_margin_percent'], cost_floor=summary['cost_floor']))


@router.get('')
def list_catalog(q: str = Query(default='', max_length=240),
                 quality: Literal['all', 'reliable', 'ambiguous', 'insufficient', 'no_match', 'unavailable'] = 'all',
                 freshness: Literal['all', 'current', 'outdated', 'none'] = 'all',
                 sort: Literal['sku', 'margin', 'cost_floor', 'updated'] = 'sku',
                 offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    latest_id = select(CatalogAnalysis.history_id).join(AnalysisHistory).where(
        CatalogAnalysis.product_id == CatalogProduct.id).order_by(
        AnalysisHistory.created_at.desc(), AnalysisHistory.id.desc()).limit(1).correlate(CatalogProduct).scalar_subquery()
    query = db.query(CatalogProduct, CatalogAnalysis).outerjoin(
        CatalogAnalysis, CatalogAnalysis.history_id == latest_id).filter(CatalogProduct.user_id == user.id)
    if q.strip():
        term = '%' + q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        query = query.filter(or_(CatalogProduct.product_name.ilike(term, escape='\\'),
                                 CatalogProduct.sku.ilike(term, escape='\\')))
    if quality != 'all':
        query = query.filter(CatalogAnalysis.quality == quality)
    if freshness == 'none':
        query = query.filter(CatalogAnalysis.history_id.is_(None))
    elif freshness in {'current', 'outdated'}:
        query = query.filter(CatalogAnalysis.fingerprint == CatalogProduct.fingerprint if freshness == 'current'
                             else CatalogAnalysis.fingerprint != CatalogProduct.fingerprint)
    total = query.count()
    order = {'sku': CatalogProduct.sku.asc(), 'updated': CatalogProduct.updated_at.desc(),
             'margin': CatalogAnalysis.net_margin.desc().nullslast(),
             'cost_floor': CatalogAnalysis.cost_floor.asc().nullslast()}[sort]
    rows = query.order_by(order, CatalogProduct.id).offset(offset).limit(limit).all()
    return {'items': [product_json(db, product, analysis) for product, analysis in rows], 'total': total,
            'offset': offset, 'limit': limit}


@router.post('/import')
def import_products(payload: CatalogImport, user: User = Depends(current_user), db: Session = Depends(get_db)):
    keys = [sku_key(p.fields.sku) for p in payload.products]
    if len(set(keys)) != len(keys):
        raise HTTPException(422, 'duplicate_catalog_sku')
    # Import only adds products. Existing SKUs are edited with a revision check.
    existing = db.query(CatalogProduct).filter(CatalogProduct.user_id == user.id, CatalogProduct.sku_key.in_(keys)).all()
    by_key = {p.sku_key: p for p in existing}
    products = []
    try:
        for item, key in zip(payload.products, keys):
            encoded = json.dumps(item.fields.model_dump(), ensure_ascii=False)
            product = by_key.get(key)
            if product:
                if json.loads(product.fields_json) != item.fields.model_dump() or product.stock != item.stock:
                    raise HTTPException(409, 'catalog_sku_exists')
            else:
                product = CatalogProduct(user_id=user.id, sku_key=key, sku=item.fields.sku, product_name=item.fields.product_name,
                                         fields_json=encoded, fingerprint=fingerprint(item.fields), stock=item.stock)
                db.add(product)
                db.flush()
                save_revision(db, product)
            products.append(product)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'catalog_sku_exists') from None
    return {'items': [product_json(db, product) for product in products]}


@router.post('/analyze')
def analyze_products(payload: AnalyzeSelection, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    # A lost response must return the original durable job even after later edits.
    from app.models import AnalysisBatch
    require_device(db, user, request)
    existing = db.query(AnalysisBatch).filter_by(user_id=user.id, client_id=str(payload.client_id)).first()
    if existing:
        return batch_json(db, existing)
    products = selected(db, user, payload)
    batch = BatchCreate(client_id=payload.client_id,
                        rows=[BatchRow(line=index+1, fields=AnalysisFields.model_validate_json(p.fields_json))
                              for index, p in enumerate(products)])
    return store_batch(db, user, batch)


@router.post('/monitor')
def monitor_products(payload: Selection, user: User = Depends(current_user), db: Session = Depends(get_db)):
    products = selected(db, user, payload)
    try:
        for product in products:
            fields = json.loads(product.fields_json)
            # Setting a claim also detects an edit from another device mid-request.
            changed = db.query(CatalogProduct).filter_by(id=product.id, revision=product.revision,
                                                         watch_id=product.watch_id).update({'updated_at': now()}, synchronize_session=False)
            if not changed:
                raise HTTPException(409, 'catalog_revision_conflict')
            watch = db.get(ProductWatch, product.watch_id) if product.watch_id else None
            if watch is None:
                watch = ProductWatch(user_id=user.id)
                db.add(watch)
            watch.product_name, watch.variant_text, watch.country = fields['product_name'], fields['variant_text'], fields['destination_country']
            watch.settings_json = json.dumps({**fields, 'autopilot_enabled': False}, ensure_ascii=False)
            watch.active, watch.autopilot_enabled, watch.updated_at = True, False, now()
            db.flush()
            product.watch_id = watch.id
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'catalog_revision_conflict') from None
    return {'items': [product_json(db, p) for p in products]}


@router.put('/{product_id}')
def update_product(product_id: str, payload: ProductUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    product = owned(db, user, product_id)
    fields = payload.fields.model_dump()
    if fields['sku'] != json.loads(product.fields_json)['sku']:
        raise HTTPException(422, 'catalog_sku_immutable')
    values = {'fields_json': json.dumps(fields, ensure_ascii=False), 'product_name': fields['product_name'],
              'fingerprint': fingerprint(payload.fields), 'stock': payload.stock, 'revision': payload.revision+1, 'updated_at': now()}
    if not db.query(CatalogProduct).filter_by(id=product.id, revision=payload.revision).update(values, synchronize_session=False):
        raise HTTPException(409, 'catalog_revision_conflict')
    db.refresh(product)
    save_revision(db, product)
    # Keep an active monitor aligned with the saved costs. Never reactivate a paused watch.
    watch = db.get(ProductWatch, product.watch_id) if product.watch_id else None
    if watch:
        settings = json.loads(watch.settings_json)
        watch.product_name, watch.variant_text, watch.country = fields['product_name'], fields['variant_text'], fields['destination_country']
        watch.settings_json = json.dumps({**settings, **fields}, ensure_ascii=False)
        watch.updated_at = now()
    db.commit()
    return product_json(db, product)


@router.get('/{product_id}/revisions')
def revisions(product_id: str, offset: int = Query(default=0, ge=0), user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned(db, user, product_id)
    query = db.query(CatalogRevision).filter_by(product_id=product_id)
    total = query.count()
    rows = query.order_by(CatalogRevision.revision.desc()).offset(offset).limit(20).all()
    return {'items': [{'revision': row.revision, 'fields': json.loads(row.fields_json), 'stock': row.stock,
                       'created_at': iso(row.created_at)} for row in rows], 'total': total, 'offset': offset}


@router.delete('/{product_id}')
def delete_product(product_id: str, revision: int = Query(ge=1), user: User = Depends(current_user), db: Session = Depends(get_db)):
    product = owned(db, user, product_id)
    if not db.query(CatalogProduct).filter_by(id=product.id, revision=revision).update({'updated_at': now()}, synchronize_session=False):
        raise HTTPException(409, 'catalog_revision_conflict')
    watch = db.get(ProductWatch, product.watch_id) if product.watch_id else None
    if watch:
        watch.active, watch.updated_at = False, now()
    db.query(CatalogAnalysis).filter_by(product_id=product.id).delete(synchronize_session=False)
    db.query(CatalogRevision).filter_by(product_id=product.id).delete(synchronize_session=False)
    db.delete(product)
    db.commit()
    return {'ok': True}
