"""Account-scoped history; imported summaries are never treated as market evidence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import AnalysisHistory, User

router = APIRouter(prefix="/v1/history", tags=["history"])


def aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def history_json(row):
    return {**json.loads(row.summary_json), "id": row.id,
            "date": aware(row.created_at).isoformat(), "imported": row.payload_json is None}


def record_analysis(db, user, result):
    pricing = result.get("pricing") or {}
    market = result.get("market") or {}
    rec = (pricing.get("strategies") or {}).get("recommended") or {}
    request = result.get("request") or {}
    summary = {
        "name": (result.get("product") or {}).get("product_name") or request.get("product_name") or "",
        "recommended": rec.get("price"),
        "score": (pricing.get("opportunity") or {}).get("score") if market.get("reliable") else None,
        "marketMedian": (pricing.get("market") or {}).get("median") if market.get("reliable") else None,
        "mode": (market.get("quality") or {}).get("state", "unavailable"),
        "form": request,
    }
    row = AnalysisHistory(user_id=user.id, summary_json=json.dumps(summary, ensure_ascii=False),
                          payload_json=json.dumps(result, ensure_ascii=False, allow_nan=False))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


class ImportedSummary(BaseModel):
    client_id: str
    date: datetime
    name: str = Field(min_length=1, max_length=240)
    recommended: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    score: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    marketMedian: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    mode: str = Field(default="unavailable", max_length=32)

    @field_validator("client_id")
    @classmethod
    def valid_id(cls, value):
        return str(UUID(value))


class HistoryImport(BaseModel):
    items: list[ImportedSummary] = Field(max_length=80)


@router.get("")
def list_history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(AnalysisHistory).filter_by(user_id=user.id).order_by(
        AnalysisHistory.created_at.desc(), AnalysisHistory.id.desc()).limit(80).all()
    return {"items": [history_json(row) for row in rows]}


@router.post("/import")
def import_history(payload: HistoryImport, user: User = Depends(current_user), db: Session = Depends(get_db)):
    for item in payload.items:
        if db.query(AnalysisHistory).filter_by(user_id=user.id, client_id=item.client_id).first():
            continue
        summary = item.model_dump(exclude={"client_id", "date"})
        try:
            with db.begin_nested():
                db.add(AnalysisHistory(user_id=user.id, client_id=item.client_id,
                                      created_at=aware(item.date).astimezone(timezone.utc), summary_json=json.dumps(summary)))
                db.flush()
        except IntegrityError:
            # The same device may retry an import after a lost response.
            if not db.query(AnalysisHistory).filter_by(user_id=user.id, client_id=item.client_id).first():
                raise
    db.commit()
    return list_history(user, db)


@router.delete("")
def clear_history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.query(AnalysisHistory).filter_by(user_id=user.id).delete(synchronize_session=False)
    db.commit()
    return {"ok": True}


@router.get("/{analysis_id}")
def get_history(analysis_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.query(AnalysisHistory).filter_by(id=analysis_id, user_id=user.id).first()
    if not row:
        raise HTTPException(404, "analysis_not_found")
    return {"item": history_json(row), "analysis": json.loads(row.payload_json) if row.payload_json else None}
