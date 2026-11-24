"""Operational status and bounded retries for the embedded Sentinel."""

import asyncio
from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import text

RETRY_LIMIT = 3
log = logging.getLogger("marketai.local")


class LocalMonitor:
    def __init__(self):
        self.next_check = None
        self.lock = asyncio.Lock()
        self.current_product = None
        self.cycle_failed = False

    def initialize(self):
        from app.db import engine
        with engine.begin() as db:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS local_collection_failures (
                    watch_id TEXT PRIMARY KEY,
                    failed_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL
                )
            """))

    def _finish(self, watch_id, succeeded, *, retry):
        from app.db import engine
        with engine.begin() as db:
            if succeeded:
                db.execute(text("DELETE FROM local_collection_failures WHERE watch_id=:id"),
                           {"id": watch_id})
            else:
                db.execute(text("""
                    INSERT INTO local_collection_failures(watch_id, failed_at, attempts)
                    VALUES (:id, :at, :attempts)
                    ON CONFLICT(watch_id) DO UPDATE SET
                        failed_at=excluded.failed_at,
                        attempts=local_collection_failures.attempts + excluded.attempts
                """), {"id": watch_id, "at": datetime.now(timezone.utc).isoformat(),
                       "attempts": int(retry)})

    async def collect(self, db, watch, user, *, retry=False):
        from app.sentinel_worker import check_one
        self.current_product = watch.product_name
        try:
            succeeded = await check_one(db, watch, user, require_working_source=True)
            self._finish(watch.id, succeeded, retry=retry)
            return succeeded
        finally:
            self.current_product = None

    async def run(self):
        from app.sentinel_worker import cycle, INTERVAL
        while True:
            async with self.lock:
                self.next_check = None
                try:
                    await cycle(collect=self.collect)
                    self.cycle_failed = False
                except Exception:
                    self.cycle_failed = True
                    log.exception("Local monitoring cycle failed")
                finally:
                    self.next_check = (datetime.now(timezone.utc) + timedelta(minutes=INTERVAL)).isoformat()
            await asyncio.sleep(INTERVAL * 60)

    async def retry(self, watch_id):
        from app.db import SessionLocal
        from app.models import ProductWatch, User
        if self.lock.locked():
            return "monitor_busy"
        async with self.lock:
            with SessionLocal() as db:
                watch = db.get(ProductWatch, watch_id)
                if not watch or not watch.active:
                    return "failure_not_found"
                user = db.get(User, watch.user_id)
                if not user or user.status != "active" or user.deleted_at is not None:
                    return "failure_not_found"
                attempts = db.execute(text(
                    "SELECT attempts FROM local_collection_failures WHERE watch_id=:id"
                ), {"id": watch_id}).scalar()
                if attempts is None:
                    return "failure_not_found"
                if attempts >= RETRY_LIMIT:
                    return "retry_limit"
                result = await self.collect(db, watch, user, retry=True)
                return "collected" if result else "collection_failed"

    def status(self):
        from app.db import SessionLocal
        from app.models import AnalysisBatch, MarketSnapshot
        with SessionLocal() as db:
            last = db.query(MarketSnapshot.created_at).order_by(
                MarketSnapshot.created_at.desc()
            ).limit(1).scalar()
            failures = db.execute(text("""
                SELECT w.id, w.product_name, f.failed_at, f.attempts
                FROM local_collection_failures f JOIN product_watches w ON w.id=f.watch_id
                WHERE w.active ORDER BY f.failed_at DESC LIMIT 100
            """)).mappings().all()
            active_batches = db.query(AnalysisBatch).filter(
                AnalysisBatch.status.in_(("queued", "running"))
            ).count()
        return {
            "last_collection": last.replace(tzinfo=timezone.utc).isoformat() if last else None,
            "next_check": self.next_check,
            "running": self.lock.locked(),
            "current_product": self.current_product,
            "cycle_failed": self.cycle_failed,
            "active_batches": active_batches,
            "retry_limit": RETRY_LIMIT,
            "failures": [dict(row) for row in failures],
        }
