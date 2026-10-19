from datetime import timedelta
from uuid import UUID

from celery import Celery
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import Principal, require_roles
from app.core.ingestion_runs import expire_stale_runs
from app.core.source_policy import source_is_publishable
from app.db.session import get_db
from app.models.entities import AuditLog, IngestionError, IngestionRun, Source, SourceCheckpoint, SourceDocument, SourceRecord, utcnow
from app.schemas.sources import APPROVED_LICENSE_STATUSES

router = APIRouter(prefix="/ingestion", tags=["ingestion"])
require_admin = require_roles("admin")
require_document_reader = require_roles("analyst", "reviewer", "publisher", "admin")
dispatcher = Celery("mcho_api_dispatch", broker=settings.redis_url)


@router.get("/configuration")
def ingestion_configuration(
    principal: Principal = Depends(require_admin),
):
    """Return safe configuration status, not provider credentials or live-source claims."""
    country_scope = [item.strip() for item in settings.reliefweb_countries.split(",") if item.strip()]
    appname_configured = bool(settings.reliefweb_appname.strip())
    return {
        "provider": "reliefweb_reports",
        "configured_in_api_environment": bool(appname_configured and country_scope),
        "appname_configured": appname_configured,
        "country_scope": country_scope,
        "limits": {
            "initial_lookback_days": settings.reliefweb_initial_lookback_days,
            "max_pages": settings.reliefweb_max_pages,
            "page_size": settings.reliefweb_page_size,
            "overlap_hours": settings.reliefweb_overlap_hours,
        },
        "note": "This is API-side configuration only, not a live connectivity test. Match RELIEFWEB_APPNAME and RELIEFWEB_COUNTRIES in the worker environment before queueing runs.",
    }


def _run_dict(run: IngestionRun) -> dict:
    return {
        "id": str(run.id), "source_id": str(run.source_id), "task_id": run.task_id,
        "trigger": run.trigger, "status": run.status, "adapter_name": run.adapter_name,
        "adapter_version": run.adapter_version, "requested_by": run.requested_by,
        "cursor_in": run.cursor_in, "cursor_out": run.cursor_out,
        "pages_fetched": run.pages_fetched, "records_fetched": run.records_fetched,
        "records_created": run.records_created, "records_updated": run.records_updated,
        "records_unchanged": run.records_unchanged, "records_failed": run.records_failed,
        "error_summary": run.error_summary, "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


@router.post("/sources/{source_id}/runs", status_code=status.HTTP_202_ACCEPTED)
def queue_source_run(
    source_id: UUID,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    if source.source_type != "reliefweb_reports":
        raise HTTPException(status_code=409, detail="No ingestion adapter is implemented for this source type.")
    if not settings.reliefweb_appname.strip() or not any(
        item.strip() for item in settings.reliefweb_countries.split(",")
    ):
        raise HTTPException(
            status_code=409,
            detail="ReliefWeb adapter configuration is incomplete in the API environment. Set RELIEFWEB_APPNAME and RELIEFWEB_COUNTRIES in both API and worker services.",
        )
    if not source_is_publishable(source):
        raise HTTPException(status_code=409, detail="Source is inactive or terms/retention policy are not reviewed.")
    expire_stale_runs(db, source.id)
    db.flush()
    active_run = db.scalar(
        select(IngestionRun.id).where(
            IngestionRun.source_id == source.id,
            IngestionRun.status.in_(["queued", "running", "retrying"]),
        ).limit(1)
    )
    if active_run is not None:
        raise HTTPException(status_code=409, detail="An ingestion run for this source is already queued or running.")

    run = IngestionRun(
        source_id=source.id, trigger="manual", status="queued", adapter_name="reliefweb_reports",
        adapter_version="1", requested_by=principal.identity,
    )
    db.add(run)
    db.flush()
    db.add(AuditLog(
        actor_id=principal.identity, action="ingestion_run_queued",
        subject_type="source", subject_id=str(source.id),
        detail={"run_id": str(run.id), "adapter": run.adapter_name, "issuer": principal.issuer},
    ))
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An ingestion run could not be queued; check active runs.") from exc

    try:
        task = dispatcher.send_task("mcho.ingest_source", args=[str(source.id), str(run.id)])
        run.task_id = task.id
        db.commit()
    except Exception as exc:
        db.rollback()
        failed = db.get(IngestionRun, run.id)
        if failed:
            failed.status = "queue_failed"
            failed.error_summary = "Task queue unavailable; no provider request was started."
            failed.finished_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            db.add(AuditLog(
                actor_id=principal.identity, action="ingestion_dispatch_failed",
                subject_type="ingestion_run", subject_id=str(run.id),
                detail={"source_id": str(source.id), "issuer": principal.issuer},
            ))
            db.commit()
        raise HTTPException(status_code=503, detail="Task queue unavailable; ingestion was not started.") from exc

    db.refresh(run)
    return _run_dict(run)


@router.get("/operations")
def operations_summary(
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Read-only operational snapshot; reports timestamps and states, not inferred truth."""
    now = utcnow()
    provider_countries = [item.strip() for item in settings.reliefweb_countries.split(",") if item.strip()]
    provider_configured = bool(settings.reliefweb_appname.strip() and provider_countries)

    sources = db.scalars(select(Source).order_by(Source.name.asc())).all()
    source_ids = [source.id for source in sources]
    checkpoints = {}
    if source_ids:
        checkpoints = {
            item.source_id: item
            for item in db.scalars(
                select(SourceCheckpoint).where(SourceCheckpoint.source_id.in_(source_ids))
            ).all()
        }

    latest_times = (
        select(
            IngestionRun.source_id.label("source_id"),
            func.max(IngestionRun.created_at).label("latest_created_at"),
        )
        .group_by(IngestionRun.source_id)
        .subquery()
    )
    latest_runs = db.scalars(
        select(IngestionRun).join(
            latest_times,
            and_(
                IngestionRun.source_id == latest_times.c.source_id,
                IngestionRun.created_at == latest_times.c.latest_created_at,
            ),
        )
    ).all()
    latest_run_by_source = {run.source_id: run for run in latest_runs}

    cutoff = now - timedelta(hours=24)
    recent_runs = db.scalars(
        select(IngestionRun).where(IngestionRun.created_at >= cutoff)
    ).all()
    run_status_counts: dict[str, int] = {}
    for run in recent_runs:
        run_status_counts[run.status] = run_status_counts.get(run.status, 0) + 1

    active_run_count = sum(
        1 for run in latest_runs if run.status in {"queued", "running", "retrying"}
    )
    source_rows = []
    never_ingested_count = 0
    terms_review_required_count = 0
    provider_missing_count = 0
    active_source_count = 0
    for source in sources:
        checkpoint = checkpoints.get(source.id)
        last_run = latest_run_by_source.get(source.id)
        reviewed_terms = bool(
            source.license_status in APPROVED_LICENSE_STATUSES
            and source.terms_reviewed_at
            and source.terms_reviewed_by
            and source.license_terms_url
            and source.retention_policy
        )
        if not reviewed_terms:
            terms_review_required_count += 1
        if source.active:
            active_source_count += 1
        if source.active and source.source_type == "reliefweb_reports" and not provider_configured:
            provider_missing_count += 1

        if not source.active:
            operational_state = "inactive"
        elif not reviewed_terms:
            operational_state = "terms_review_required"
        elif source.source_type == "reliefweb_reports" and not provider_configured:
            operational_state = "provider_configuration_missing"
        elif checkpoint is None:
            operational_state = "never_ingested"
            never_ingested_count += 1
        elif last_run is not None:
            operational_state = last_run.status
        else:
            operational_state = "checkpoint_without_run"

        checkpoint_updated_at = checkpoint.updated_at if checkpoint else None
        hours_since_checkpoint = (
            round((now - checkpoint_updated_at).total_seconds() / 3600, 2)
            if checkpoint_updated_at else None
        )
        cursor = checkpoint.cursor_json if checkpoint else {}
        source_rows.append({
            "id": str(source.id),
            "name": source.name,
            "source_type": source.source_type,
            "active": source.active,
            "license_status": source.license_status,
            "terms_reviewed": reviewed_terms,
            "operational_state": operational_state,
            "latest_run_status": last_run.status if last_run else None,
            "latest_run_created_at": last_run.created_at.isoformat() if last_run else None,
            "latest_run_finished_at": last_run.finished_at.isoformat() if last_run and last_run.finished_at else None,
            "latest_checkpoint_updated_at": checkpoint_updated_at.isoformat() if checkpoint_updated_at else None,
            "latest_watermark": cursor.get("latest_watermark"),
            "hours_since_checkpoint": hours_since_checkpoint,
        })

    return {
        "generated_at": now.isoformat(),
        "provider_configured_in_api_environment": provider_configured,
        "source_counts": {
            "total": len(sources),
            "active": active_source_count,
            "terms_review_required": terms_review_required_count,
            "provider_configuration_missing": provider_missing_count,
            "never_ingested": never_ingested_count,
        },
        "active_runs": active_run_count,
        "runs_created_last_24h": {
            "total": len(recent_runs),
            "by_status": run_status_counts,
        },
        "sources": source_rows,
        "note": "Manual-ingestion status and timestamps only. No periodic polling is configured; timestamps do not certify source truth or upstream connectivity.",
    }


@router.get("/runs")
def list_runs(
    source_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = select(IngestionRun)
    if source_id:
        query = query.where(IngestionRun.source_id == source_id)
    rows = db.scalars(query.order_by(IngestionRun.created_at.desc()).limit(limit)).all()
    return {"items": [_run_dict(run) for run in rows]}


@router.get("/runs/{run_id}/errors")
def list_run_errors(
    run_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    run = db.get(IngestionRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Ingestion run not found.")
    rows = db.scalars(
        select(IngestionError).where(IngestionError.run_id == run_id)
        .order_by(IngestionError.created_at.desc()).limit(limit)
    ).all()
    return {"run_id": str(run_id), "items": [
        {"id": str(row.id), "external_id": row.external_id, "error_code": row.error_code,
         "error_summary": row.error_summary, "row_sha256": row.row_sha256,
         "created_at": row.created_at.isoformat()}
        for row in rows
    ], "note": "Errors store a hash and sanitized category only, not the source payload."}


@router.get("/documents")
def list_source_documents(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100000),
    review_status: str | None = Query(default=None, pattern="^(pending_review|approved|provisional|disputed|rejected|needs_more_evidence)$"),
    source_id: UUID | None = None,
    principal: Principal = Depends(require_document_reader),
    db: Session = Depends(get_db),
):
    query = select(SourceDocument, Source.name).join(Source, SourceDocument.source_id == Source.id)
    if review_status:
        query = query.where(SourceDocument.review_status == review_status)
    if source_id:
        query = query.where(SourceDocument.source_id == source_id)
    rows = db.execute(query.order_by(SourceDocument.retrieved_at.desc()).offset(offset).limit(limit)).all()
    items = []
    for document, source_name in rows:
        external_ids = db.scalars(
            select(SourceRecord.external_id).where(SourceRecord.source_document_id == document.id)
        ).all()
        items.append({
            "id": str(document.id), "source_id": str(document.source_id), "source_name": source_name,
            "title": document.title, "canonical_url": document.canonical_url,
            "published_at": document.published_at.isoformat() if document.published_at else None,
            "retrieved_at": document.retrieved_at.isoformat(), "content_hash": document.content_hash,
            "license_note": document.license_note, "metadata": document.metadata_json,
            "review_status": document.review_status, "reviewed_by": document.reviewed_by,
            "reviewed_at": document.reviewed_at.isoformat() if document.reviewed_at else None,
            "review_rationale": document.review_rationale, "external_ids": external_ids,
        })
    return {"items": items, "offset": offset, "limit": limit,
            "note": "Source metadata and links only; article bodies are not stored by this connector."}


@router.get("/documents/{document_id}")
def get_source_document(
    document_id: UUID,
    principal: Principal = Depends(require_document_reader),
    db: Session = Depends(get_db),
):
    document = db.get(SourceDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Source document not found.")
    source = db.get(Source, document.source_id)
    records = db.scalars(select(SourceRecord).where(SourceRecord.source_document_id == document.id)).all()
    return {
        "id": str(document.id), "source_id": str(document.source_id),
        "source_name": source.name if source else None,
        "title": document.title, "canonical_url": document.canonical_url,
        "published_at": document.published_at.isoformat() if document.published_at else None,
        "retrieved_at": document.retrieved_at.isoformat(), "content_hash": document.content_hash,
        "license_note": document.license_note, "metadata": document.metadata_json,
        "review_status": document.review_status, "reviewed_by": document.reviewed_by,
        "reviewed_at": document.reviewed_at.isoformat() if document.reviewed_at else None,
        "review_rationale": document.review_rationale,
        "external_ids": [record.external_id for record in records],
        "note": "This record contains metadata and a source link only; it is not an independently verified event.",
    }
