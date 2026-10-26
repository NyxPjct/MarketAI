from __future__ import annotations
import asyncio, json, os
from datetime import datetime, timezone
from app.db import SessionLocal, Base, engine
from app.models import ProductWatch, User
from app.market_engine import run_analysis

INTERVAL=max(15,int(os.getenv("SENTINEL_INTERVAL_MINUTES","60")))
BATCH=max(1,int(os.getenv("SENTINEL_BATCH_SIZE","50")))

def utcnow(): return datetime.now(timezone.utc)

async def check_one(db,w,user):
    try:
        fields=json.loads(w.settings_json or "{}")
        fields.update({"product_name":w.product_name,"variant_text":w.variant_text,"destination_country":w.country})
        analysis=await run_analysis(fields)
        from app.watch_collection import persist_snapshot, record_failure
        persist_snapshot(db,w,analysis,fields)
        db.commit()
    except Exception:
        from app.watch_collection import record_failure
        db.rollback();record_failure(db,w);db.commit()

async def cycle():
    db=SessionLocal()
    try:
        rows=db.query(ProductWatch).filter_by(active=True).order_by(ProductWatch.updated_at.asc()).limit(BATCH).all()
        for w in rows:
            user=db.get(User,w.user_id)
            if user and user.status=="active" and user.deleted_at is None: await check_one(db,w,user)
        # Staleness must also be checked for active watches beyond this collection batch.
        from app.alert_rules import check_staleness
        from app.models import WatchAlertRules
        from sqlalchemy import select
        eligible=select(User.id).where(User.status=='active',User.deleted_at.is_(None))
        last_id=''
        while True:
            page=db.query(ProductWatch).join(WatchAlertRules).filter(ProductWatch.active.is_(True),ProductWatch.id>last_id,
                ProductWatch.user_id.in_(eligible)).order_by(ProductWatch.id).limit(200).all()
            if not page:break
            for watch in page:check_staleness(db,watch)
            last_id=page[-1].id
            db.commit()
    finally: db.close()

async def main():
    Base.metadata.create_all(engine)
    while True:
        await cycle(); await asyncio.sleep(INTERVAL*60)

if __name__=="__main__": asyncio.run(main())
