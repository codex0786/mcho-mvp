"""Lifecycle rules for ingestion runs shared by the API and the worker.

A worker that dies mid-run leaves its run in an active state. Because only one
active run is allowed per source, such a run would block that source forever.
Runs that stay active past ``settings.ingestion_stale_run_minutes`` are treated
as abandoned: the API expires them before queueing, and a redelivered task may
take one over.
"""
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import AuditLog, IngestionRun, utcnow

ACTIVE_RUN_STATUSES = ("queued", "running", "retrying")
STALE_RUN_SUMMARY = "Run stayed active past the stale-run timeout without finishing; marked failed so the source can run again."


def stale_run_timeout() -> timedelta:
    return timedelta(minutes=settings.ingestion_stale_run_minutes)


def run_is_stale(run: Any, now: datetime, timeout: timedelta | None = None) -> bool:
    """Active and with no progress marker newer than the timeout."""
    if run.status not in ACTIVE_RUN_STATUSES:
        return False
    last_activity = run.started_at or run.created_at
    return last_activity < now - (timeout or stale_run_timeout())


def expire_stale_runs(db: Session, source_id: UUID, now: datetime | None = None) -> int:
    """Mark this source's abandoned runs failed (in the caller's transaction)."""
    now = now or utcnow()
    candidates = db.scalars(
        select(IngestionRun)
        .where(IngestionRun.source_id == source_id, IngestionRun.status.in_(ACTIVE_RUN_STATUSES))
        .with_for_update()
    ).all()
    expired = 0
    for run in candidates:
        if not run_is_stale(run, now):
            continue
        previous_status = run.status
        run.status = "failed"
        run.error_summary = STALE_RUN_SUMMARY
        run.finished_at = now
        db.add(AuditLog(
            actor_id="system:stale-run-reaper", action="ingestion_run_expired",
            subject_type="ingestion_run", subject_id=str(run.id),
            detail={"source_id": str(source_id), "previous_status": previous_status,
                    "timeout_minutes": settings.ingestion_stale_run_minutes},
        ))
        expired += 1
    return expired
