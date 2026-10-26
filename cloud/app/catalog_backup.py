"""Full catalog input archives, with reviewed, atomic, retry-safe restoration."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.alert_rules import AlertRules, rules_for, store_rules
from app.catalog import CatalogFields, fingerprint, sku_key
from app.batches import iso, now
from app.db import get_db
from app.deps import current_user
from app.models import CatalogProduct, CatalogRevision, CatalogRevisionSource, CatalogRestore, ProductWatch, User

router = APIRouter(prefix='/v1/catalog/backup', tags=['catalog backup'])
MAX_BACKUP_BYTES = 10 * 1024 * 1024
MAX_PRODUCTS = 5000
MAX_REVISIONS = 50000


class ArchiveModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SavedRevision(ArchiveModel):
    revision: int = Field(ge=1)
    fields: CatalogFields
    stock: int = Field(ge=0, le=1_000_000_000)
    created_at: datetime
    restored: bool = False

    @field_validator('created_at')
    @classmethod
    def timestamp(cls, value):
        if value.tzinfo is None:
            raise ValueError('timezone_required')
        return value.astimezone(timezone.utc)


class SavedProduct(ArchiveModel):
    fields: CatalogFields
    stock: int = Field(ge=0, le=1_000_000_000)
    created_at: datetime
    revisions: list[SavedRevision] = Field(min_length=1, max_length=MAX_REVISIONS)
    monitoring_was_active: bool
    alert_rules: AlertRules | None

    @model_validator(mode='after')
    def consistent_history(self):
        if self.created_at.tzinfo is None:
            raise ValueError('timezone_required')
        for index, row in enumerate(self.revisions):
            if row.revision != index+1 or row.fields.sku != self.fields.sku:
                raise ValueError('invalid_revision_sequence')
        last = self.revisions[-1]
        if last.fields != self.fields or last.stock != self.stock:
            raise ValueError('current_revision_mismatch')
        return self


class CatalogArchive(ArchiveModel):
    format: Literal['MarketAICatalogBackup']
    version: Literal[1]
    account_id: UUID
    exported_at: datetime
    products: list[SavedProduct] = Field(max_length=MAX_PRODUCTS)

    @model_validator(mode='after')
    def unique_products(self):
        keys = [sku_key(row.fields.sku) for row in self.products]
        if len(set(keys)) != len(keys) or sum(len(row.revisions) for row in self.products) > MAX_REVISIONS:
            raise ValueError('duplicate_skus_or_too_many_revisions')
        if self.exported_at.tzinfo is None:
            raise ValueError('timezone_required')
        return self


class RestoreRef(ArchiveModel):
    sku: str = Field(min_length=1, max_length=120)
    expected_id: UUID | None
    expected_revision: int | None = Field(ge=1)
    expected_watch_id: UUID | None
    expected_rules_revision: int = Field(ge=0)


class RestorePlan(ArchiveModel):
    client_id: UUID
    digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    products: list[RestoreRef] = Field(min_length=1, max_length=MAX_PRODUCTS)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def read_archive(content, user):
    if len(content) > MAX_BACKUP_BYTES:
        raise HTTPException(413, 'catalog_backup_too_large')
    try:
        archive = CatalogArchive.model_validate(json.loads(content.decode('utf-8-sig'), object_pairs_hook=no_duplicate_keys))
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(422, 'catalog_backup_invalid') from None
    if str(archive.account_id) != user.id:
        raise HTTPException(403, 'catalog_backup_wrong_account')
    return archive


def current_ref(db, product):
    watch = db.get(ProductWatch, product.watch_id) if product.watch_id else None
    revision = rules_for(db, watch)[1] if watch else 0
    return {'expected_id': product.id, 'expected_revision': product.revision,
            'expected_watch_id': product.watch_id, 'expected_rules_revision': revision}


@router.get('')
def export_backup(user: User = Depends(current_user), db: Session = Depends(get_db)):
    products = db.query(CatalogProduct).filter_by(user_id=user.id).with_for_update().order_by(CatalogProduct.sku).limit(MAX_PRODUCTS+1).all()
    if len(products) > MAX_PRODUCTS:
        raise HTTPException(413, 'catalog_backup_too_large')
    rows = []
    revision_count = 0
    for product in products:
        revisions = db.query(CatalogRevision).filter_by(product_id=product.id).order_by(CatalogRevision.revision).all()
        revision_count += len(revisions)
        if revision_count > MAX_REVISIONS:
            raise HTTPException(413, 'catalog_backup_too_large')
        restored = {item.revision_id for item in db.query(CatalogRevisionSource).filter(
            CatalogRevisionSource.revision_id.in_([row.id for row in revisions])).all()}
        watch = db.get(ProductWatch, product.watch_id) if product.watch_id else None
        rows.append({'fields': json.loads(product.fields_json), 'stock': product.stock, 'created_at': iso(product.created_at),
            'revisions': [{'revision': row.revision, 'fields': json.loads(row.fields_json), 'stock': row.stock,
                           'created_at': iso(row.created_at), 'restored': row.id in restored} for row in revisions],
            'monitoring_was_active': bool(watch and watch.active),
            'alert_rules': rules_for(db, watch)[0].model_dump() if watch else None})
    archive = CatalogArchive(format='MarketAICatalogBackup', version=1, account_id=user.id, exported_at=now(), products=rows)
    content = archive.model_dump_json(indent=2).encode('utf-8')
    if len(content) > MAX_BACKUP_BYTES:
        raise HTTPException(413, 'catalog_backup_too_large')
    return Response(content, media_type='application/json', headers={
        'Content-Disposition': 'attachment; filename=MarketAI-catalog-backup.json', 'Cache-Control': 'no-store'})


@router.post('/preview')
async def preview_backup(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    content = await file.read(MAX_BACKUP_BYTES+1)
    archive = read_archive(content, user)
    existing = {row.sku_key: row for row in db.query(CatalogProduct).filter_by(user_id=user.id).all()}
    rows = []
    for row in archive.products:
        product = existing.get(sku_key(row.fields.sku))
        ref = current_ref(db, product) if product else {'expected_id': None, 'expected_revision': None,
                                                        'expected_watch_id': None, 'expected_rules_revision': 0}
        rows.append({'sku': row.fields.sku, 'fields': row.fields.model_dump(), 'stock': row.stock,
                     'revisions': len(row.revisions), 'existing': product is not None,
                     'monitoring_was_active': row.monitoring_was_active, **ref})
    return {'digest': hashlib.sha256(content).hexdigest(), 'exported_at': archive.exported_at.isoformat(), 'items': rows}


def request_hash(plan):
    return hashlib.sha256(json.dumps(plan.model_dump(mode='json', exclude={'client_id'}), sort_keys=True).encode()).hexdigest()


def receipt_result(receipt, digest):
    if receipt.request_hash != digest:
        raise HTTPException(409, 'catalog_restore_key_reused')
    return json.loads(receipt.result_json)


@router.post('/restore')
async def restore_backup(file: UploadFile = File(...), plan: str = Form(...),
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    content = await file.read(MAX_BACKUP_BYTES+1)
    archive = read_archive(content, user)
    try:
        selected = RestorePlan.model_validate_json(plan)
    except ValidationError:
        raise HTTPException(422, 'catalog_backup_invalid') from None
    if hashlib.sha256(content).hexdigest() != selected.digest:
        raise HTTPException(409, 'catalog_backup_changed')
    digest = request_hash(selected)
    previous = db.query(CatalogRestore).filter_by(user_id=user.id, client_id=str(selected.client_id)).first()
    if previous:
        return receipt_result(previous, digest)
    archived = {row.fields.sku: row for row in archive.products}
    if len({sku_key(row.sku) for row in selected.products}) != len(selected.products) or any(row.sku not in archived for row in selected.products):
        raise HTTPException(422, 'catalog_backup_invalid')
    receipt = CatalogRestore(user_id=user.id, client_id=str(selected.client_id), request_hash=digest)
    result = {'created': 0, 'replaced': 0, 'revisions': 0, 'monitoring': 'paused'}
    try:
        db.add(receipt)
        db.flush()  # Unique client ID serializes retries before any catalog mutations.
        for ref in selected.products:
            saved = archived[ref.sku]
            product = db.query(CatalogProduct).filter_by(user_id=user.id, sku_key=sku_key(ref.sku)).first()
            if product:
                expected = ref.model_dump(mode='json', exclude={'sku'})
                if current_ref(db, product) != expected or product.sku != ref.sku:
                    raise HTTPException(409, 'catalog_restore_conflict')
                old_revision = product.revision
                won = db.query(CatalogProduct).filter_by(id=product.id, revision=ref.expected_revision,
                    watch_id=str(ref.expected_watch_id) if ref.expected_watch_id else None).update(
                    {'revision': old_revision+len(saved.revisions), 'updated_at': now()}, synchronize_session=False)
                if not won:
                    raise HTTPException(409, 'catalog_restore_conflict')
                db.refresh(product)
                result['replaced'] += 1
            else:
                if ref.expected_id is not None or ref.expected_revision is not None or ref.expected_watch_id is not None or ref.expected_rules_revision:
                    raise HTTPException(409, 'catalog_restore_conflict')
                old_revision = 0
                product = CatalogProduct(user_id=user.id, sku=ref.sku, sku_key=sku_key(ref.sku),
                    product_name=saved.fields.product_name, fields_json=saved.fields.model_dump_json(),
                    fingerprint=fingerprint(saved.fields), stock=saved.stock, revision=len(saved.revisions),
                    created_at=saved.created_at, updated_at=now())
                db.add(product)
                db.flush()
                result['created'] += 1
            product.fields_json, product.stock = saved.fields.model_dump_json(), saved.stock
            product.product_name, product.fingerprint = saved.fields.product_name, fingerprint(saved.fields)
            for entry in saved.revisions:
                revision = CatalogRevision(product_id=product.id, revision=old_revision+entry.revision,
                    fields_json=entry.fields.model_dump_json(), stock=entry.stock, created_at=entry.created_at)
                db.add(revision)
                db.flush()
                db.add(CatalogRevisionSource(revision_id=revision.id))
                result['revisions'] += 1
            watch = db.get(ProductWatch, product.watch_id) if product.watch_id else None
            if watch is None and saved.alert_rules is not None:
                watch = ProductWatch(user_id=user.id)
                db.add(watch)
                watch.product_name = saved.fields.product_name
                db.flush()
                product.watch_id = watch.id
            if watch:
                watch.product_name, watch.variant_text, watch.country = saved.fields.product_name, saved.fields.variant_text, saved.fields.destination_country
                watch.settings_json = json.dumps({**saved.fields.model_dump(), 'autopilot_enabled': False})
                watch.active, watch.autopilot_enabled, watch.updated_at = False, False, now()
                store_rules(db, watch, saved.alert_rules or AlertRules(), ref.expected_rules_revision)
        receipt.result_json = json.dumps(result)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        previous = db.query(CatalogRestore).filter_by(user_id=user.id, client_id=str(selected.client_id)).first()
        if previous:
            return receipt_result(previous, digest)
        raise HTTPException(409, 'catalog_restore_conflict') from None
    return result
