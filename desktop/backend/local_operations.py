"""Desktop API for operations on the current embedded profile."""

import asyncio
import logging
import sqlite3
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/local")
runtime = None
logger = logging.getLogger("marketai.local")


def local_runtime():
    if runtime is None:
        raise HTTPException(404, "local_mode_required")
    return runtime


@router.get("/backups")
def backup_status():
    try:
        return local_runtime().backup.status()
    except (OSError, UnicodeError, ValueError):
        logger.exception("Could not list database backups")
        raise HTTPException(500, "backup_failed") from None


@router.post("/backups")
def create_backup(_: dict = Body(...)):
    try:
        local_runtime().backup.create()
    except (OSError, sqlite3.Error):
        logger.exception("Manual backup failed")
        raise HTTPException(500, "backup_failed") from None
    return backup_status()


class RestoreRequest(BaseModel):
    id: str


@router.post("/backups/restore")
def restore_backup(request: RestoreRequest):
    try:
        local_runtime().backup.schedule_restore(request.id)
    except FileNotFoundError:
        raise HTTPException(404, "backup_not_found") from None
    except sqlite3.Error:
        raise HTTPException(422, "backup_invalid") from None
    except OSError:
        logger.exception("Could not schedule database restore")
        raise HTTPException(500, "restore_failed") from None
    return backup_status()


@router.delete("/backups/restore")
def cancel_restore():
    try:
        local_runtime().backup.cancel_restore()
    except OSError:
        logger.exception("Could not cancel database restore")
        raise HTTPException(500, "restore_failed") from None
    return backup_status()


@router.get("/monitor")
def monitor_status():
    return local_runtime().monitor.status()


class RetryRequest(BaseModel):
    watch_id: UUID


@router.post("/monitor/retry")
async def retry_collection(request: RetryRequest):
    local = local_runtime()
    task = asyncio.run_coroutine_threadsafe(local.monitor.retry(str(request.watch_id)), local.loop)
    try:
        result = await asyncio.shield(asyncio.wrap_future(task))
    except Exception:
        logger.exception("Monitoring retry failed")
        raise HTTPException(500, "collection_failed") from None
    if result in {"monitor_busy", "retry_limit", "failure_not_found"}:
        raise HTTPException(409, result)
    return {"result": result}
