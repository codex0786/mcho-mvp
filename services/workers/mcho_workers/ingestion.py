"""Run-level ingestion workflow and idempotent ReliefWeb metadata upserts."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.entities import (
    AuditLog, IngestionError, IngestionRun, ReviewTask, Source, SourceCheckpoint, SourceDocument,
    SourceRecord, utcnow,
)
from app.schemas.sources import APPROVED_LICENSE_STATUSES
from mcho_workers.connectors.reliefweb import ReliefWebConnector
from mcho_workers.normalization import normalize_reliefweb_record


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ensure_review_task(db: Session, document_id: UUID) -> None:
    existing = db.scalar(
        select(ReviewTask.id).where(
            ReviewTask.subject_type == "source_document", ReviewTask.subject_id == document_id
        ).limit(1)
    )
    if existing is None:
        db.add(ReviewTask(
            subject_type="source_document", subject_id=document_id, status="pending", priority="normal"
        ))


def upsert_reliefweb_record(db: Session, source: Source, row: dict[str, Any], retrieved_at: datetime) -> str:
    record = normalize_reliefweb_record(row, retrieved_at)
    source_record = db.scalar(select(SourceRecord).where(
        SourceRecord.source_id == source.id, SourceRecord.external_id == record["external_id"]
    ))
    document = db.scalar(select(SourceDocument).where(
        SourceDocument.source_id == source.id, SourceDocument.content_hash == record["content_hash"]
    ))
    if document is None:
        document = SourceDocument(
            source_id=source.id,
            title=record["title"],
            canonical_url=record["canonical_url"],
            published_at=record["published_at"],
            retrieved_at=retrieved_at,
            content_hash=record["content_hash"],
            license_note=f"Metadata link only; source terms: {source.license_terms_url or 'not specified'}",
            metadata_json=record["metadata"],
            review_status="pending_review",
        )
        db.add(document)
        db.flush()

    if source_record is None:
        source_record = SourceRecord(
            source_id=source.id,
            external_id=record["external_id"],
            source_document_id=document.id,
            latest_content_hash=record["content_hash"],
            metadata_json=record["metadata"],
            first_seen_at=retrieved_at,
            last_seen_at=retrieved_at,
        )
        db.add(source_record)
        _ensure_review_task(db, document.id)
        return "created"

    source_record.last_seen_at = retrieved_at
    source_record.metadata_json = record["metadata"]
    if source_record.latest_content_hash == record["content_hash"]:
        return "unchanged"

    source_record.source_document_id = document.id
    source_record.latest_content_hash = record["content_hash"]
    _ensure_review_task(db, document.id)
    return "updated"


def _record_row_error(db: Session, run: IngestionRun, source: Source, row: dict[str, Any], exc: Exception) -> None:
    # Persist a record hash and sanitized error category only. Do not persist raw provider
    # payloads or article content in the error table.
    try:
        serialized = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        serialized = repr(type(row))
    row_hash = hashlib.sha256(serialized.encode("utf-8", errors="replace")).hexdigest()
    external_id = row.get("id")
    db.add(IngestionError(
        run_id=run.id, source_id=source.id,
        external_id=str(external_id)[:255] if external_id is not None else None,
        error_code=type(exc).__name__,
        error_summary="Provider record failed metadata validation and was withheld.",
        row_sha256=row_hash,
    ))


def _mark_run(run: IngestionRun, status: str, message: str | None = None) -> None:
    run.status = status
    run.error_summary = message
    run.finished_at = utcnow()


def execute_ingestion(source_id_raw: str, run_id_raw: str, attempt: int = 0, max_retries: int = 5) -> dict[str, Any]:
    source_id = UUID(source_id_raw)
    run_id = UUID(run_id_raw)
    db = SessionLocal()
    connector = ReliefWebConnector()
    try:
        run = db.scalar(select(IngestionRun).where(IngestionRun.id == run_id).with_for_update())
        source = db.get(Source, source_id)
        if run is None or source is None or run.source_id != source.id:
            raise ValueError("Ingestion run or source does not exist.")
        terminal_statuses = {"completed", "completed_with_warnings", "skipped", "failed", "queue_failed"}
        if run.status in terminal_statuses:
            return {"run_id": str(run.id), "status": run.status, "detail": "This ingestion run has already reached a terminal state."}
        if run.status == "running":
            return {"run_id": str(run.id), "status": "already_running", "detail": "A worker already claimed this ingestion run."}
        run.status = "running"
        run.started_at = run.started_at or utcnow()
        run.error_summary = None
        db.commit()

        if source.source_type != "reliefweb_reports":
            _mark_run(run, "skipped", "No adapter is implemented for this source type.")
            db.commit()
            return {"run_id": str(run.id), "status": run.status, "reason": run.error_summary}
        if (not source.active or source.license_status not in APPROVED_LICENSE_STATUSES
                or not source.terms_reviewed_at or not source.terms_reviewed_by
                or not source.license_terms_url or not source.retention_policy):
            _mark_run(run, "skipped", "Source is inactive or its permitted use has not been reviewed.")
            db.commit()
            return {"run_id": str(run.id), "status": run.status, "reason": run.error_summary}
        connector_status = connector.status()
        if not connector_status.configured:
            _mark_run(run, "skipped", connector_status.message)
            db.commit()
            return {"run_id": str(run.id), "status": run.status, "reason": run.error_summary}

        checkpoint = db.scalar(select(SourceCheckpoint).where(SourceCheckpoint.source_id == source.id))
        cursor = dict(checkpoint.cursor_json) if checkpoint else {}
        now = utcnow()
        if cursor.get("window_start") and cursor.get("window_end") and int(cursor.get("next_offset", 0)) > 0:
            start = _parse_datetime(cursor.get("window_start")) or (now - timedelta(days=7))
            end = _parse_datetime(cursor.get("window_end")) or now
            offset = int(cursor.get("next_offset", 0))
        else:
            watermark = _parse_datetime(cursor.get("latest_watermark"))
            start = (watermark - timedelta(hours=connector.config.overlap_hours)) if watermark else (
                now - timedelta(days=connector.config.initial_lookback_days)
            )
            end = now
            offset = 0
        run.cursor_in = {"window_start": start.isoformat(), "window_end": end.isoformat(), "offset": offset}
        db.commit()

        complete = False
        for _ in range(connector.config.max_pages):
            rows, total = connector.fetch_page(start, end, offset)
            retrieved_at = utcnow()
            run.pages_fetched += 1
            run.records_fetched += len(rows)
            for row in rows:
                try:
                    outcome = upsert_reliefweb_record(db, source, row, retrieved_at)
                    if outcome == "created":
                        run.records_created += 1
                    elif outcome == "updated":
                        run.records_updated += 1
                    else:
                        run.records_unchanged += 1
                except (ValueError, TypeError, KeyError) as exc:
                    run.records_failed += 1
                    _record_row_error(db, run, source, row, exc)
            offset += connector.config.page_size
            complete = (not rows) or (offset >= total)
            if checkpoint is None:
                checkpoint = SourceCheckpoint(source_id=source.id, cursor_json={})
                db.add(checkpoint)
                db.flush()
            if complete:
                next_cursor = {"latest_watermark": end.isoformat(), "next_offset": 0}
            else:
                next_cursor = {
                    "latest_watermark": cursor.get("latest_watermark"),
                    "window_start": start.isoformat(), "window_end": end.isoformat(),
                    "next_offset": offset,
                }
            checkpoint.cursor_json = next_cursor
            checkpoint.last_run_id = run.id
            checkpoint.updated_at = utcnow()
            run.cursor_out = next_cursor
            db.commit()
            if complete:
                break

        final_status = "completed" if complete and run.records_failed == 0 else (
            "completed_with_warnings" if complete else "partial"
        )
        _mark_run(run, final_status, "Some provider records were malformed and withheld." if run.records_failed else None)
        db.add(AuditLog(
            actor_id="system:reliefweb-connector", action="ingestion_run_finished",
            subject_type="ingestion_run", subject_id=str(run.id),
            detail={
                "source_id": str(source.id), "status": final_status, "pages_fetched": run.pages_fetched,
                "records_fetched": run.records_fetched, "records_created": run.records_created,
                "records_updated": run.records_updated, "records_unchanged": run.records_unchanged,
                "records_failed": run.records_failed,
            },
        ))
        db.commit()
        return {
            "run_id": str(run.id), "status": run.status, "pages_fetched": run.pages_fetched,
            "records_fetched": run.records_fetched, "records_created": run.records_created,
            "records_updated": run.records_updated, "records_unchanged": run.records_unchanged,
            "records_failed": run.records_failed, "cursor_out": run.cursor_out,
        }
    except httpx.HTTPError:
        db.rollback()
        run = db.get(IngestionRun, run_id)
        if run is not None:
            if attempt >= max_retries:
                _mark_run(run, "failed", "Provider request failed after automatic retries.")
            else:
                run.status = "retrying"
                run.error_summary = "Provider request failed transiently; automatic retry scheduled."
            db.commit()
        raise
    except Exception as exc:
        db.rollback()
        run = db.get(IngestionRun, run_id)
        if run is not None:
            _mark_run(run, "failed", f"{type(exc).__name__}: ingestion stopped; inspect worker logs for details.")
            db.commit()
        raise
    finally:
        connector.close()
        db.close()
