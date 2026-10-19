from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import Principal, require_roles
from app.db.session import get_db
from app.models.entities import AuditLog, Event, EventEvidence, EventStatus, Source, SourceDocument
from app.schemas.sources import APPROVED_LICENSE_STATUSES, SourceCreateIn, SourcePatchIn

router = APIRouter(prefix="/sources", tags=["sources"])
require_admin = require_roles("admin")


def _source_dict(source: Source) -> dict:
    return {
        "id": str(source.id), "name": source.name, "source_type": source.source_type,
        "access_mode": source.access_mode, "license_status": source.license_status,
        "homepage_url": source.homepage_url, "license_terms_url": source.license_terms_url,
        "owner_name": source.owner_name, "retention_policy": source.retention_policy,
        "refresh_cadence": source.refresh_cadence,
        "terms_reviewed_at": source.terms_reviewed_at.isoformat() if source.terms_reviewed_at else None,
        "terms_reviewed_by": source.terms_reviewed_by, "active": source.active,
        "created_at": source.created_at.isoformat(),
    }


def _invalidate_unsupported_events(db: Session, source: Source, actor: str, issuer: str) -> int:
    eligible = (
        source.active and source.license_status in APPROVED_LICENSE_STATUSES
        and source.terms_reviewed_at is not None and source.terms_reviewed_by is not None
        and source.license_terms_url is not None and source.retention_policy is not None
    )
    if eligible:
        return 0
    linked_events = db.scalars(
        select(Event).join(EventEvidence, EventEvidence.event_id == Event.id)
        .join(SourceDocument, EventEvidence.source_document_id == SourceDocument.id)
        .where(SourceDocument.source_id == source.id, Event.status == EventStatus.published)
    ).unique().all()
    invalidated = 0
    for event in linked_events:
        valid_count = db.scalar(
            select(func.count()).select_from(EventEvidence)
            .join(SourceDocument, EventEvidence.source_document_id == SourceDocument.id)
            .join(Source, SourceDocument.source_id == Source.id)
            .where(
                EventEvidence.event_id == event.id,
                Source.active.is_(True),
                Source.license_status.in_(APPROVED_LICENSE_STATUSES),
                Source.terms_reviewed_at.is_not(None),
                Source.terms_reviewed_by.is_not(None),
                Source.license_terms_url.is_not(None),
                Source.retention_policy.is_not(None),
                SourceDocument.review_status == "approved",
            )
        ) or 0
        if valid_count == 0:
            event.status = EventStatus.corrected
            invalidated += 1
            db.add(AuditLog(
                actor_id=actor, action="event_unpublished_invalidated_source",
                subject_type="event", subject_id=str(event.id),
                detail={"source_id": str(source.id), "issuer": issuer,
                        "reason": "No approved, permitted evidence remains after source configuration changed."},
            ))
    return invalidated


@router.get("")
def list_sources(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Source).where(
            Source.active.is_(True),
            Source.license_status.in_(APPROVED_LICENSE_STATUSES),
            Source.terms_reviewed_at.is_not(None),
            Source.terms_reviewed_by.is_not(None),
            Source.license_terms_url.is_not(None),
            Source.retention_policy.is_not(None),
        ).order_by(Source.name.asc()).limit(limit)
    ).all()
    return {"items": [_source_dict(source) for source in rows],
            "note": "Only active, reviewed sources are listed; a listed source may still have an unconfigured connector."}


@router.get("/admin")
def list_sources_admin(
    limit: int = Query(default=200, ge=1, le=500),
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(Source).order_by(Source.created_at.desc()).limit(limit)).all()
    return {"items": [_source_dict(source) for source in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_source(
    body: SourceCreateIn,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    source = Source(
        name=body.name, source_type=body.source_type, access_mode=body.access_mode,
        homepage_url=str(body.homepage_url) if body.homepage_url else None,
        license_terms_url=str(body.license_terms_url) if body.license_terms_url else None,
        owner_name=body.owner_name, retention_policy=body.retention_policy,
        refresh_cadence=body.refresh_cadence, license_status="unreviewed", active=False,
    )
    db.add(source)
    db.flush()
    db.add(AuditLog(
        actor_id=principal.identity, action="source_registered", subject_type="source", subject_id=str(source.id),
        detail={"source_type": source.source_type, "active": False, "issuer": principal.issuer},
    ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A source with this name already exists.") from exc
    db.refresh(source)
    return _source_dict(source)


@router.patch("/{source_id}")
def update_source(
    source_id: UUID,
    body: SourcePatchIn,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found.")
    before = {
        "active": source.active, "license_status": source.license_status,
        "license_terms_url": source.license_terms_url, "retention_policy": source.retention_policy,
    }
    patch = body.model_dump(exclude_unset=True)
    terms_review_rationale = patch.pop("terms_review_rationale", None)
    if "homepage_url" in patch:
        patch["homepage_url"] = str(patch["homepage_url"]) if patch["homepage_url"] else None
    if "license_terms_url" in patch:
        patch["license_terms_url"] = str(patch["license_terms_url"]) if patch["license_terms_url"] else None
    for key, value in patch.items():
        setattr(source, key, value)

    terms_changed = (
        "license_terms_url" in patch
        and patch["license_terms_url"] != before["license_terms_url"]
    )
    if terms_changed and (
        patch.get("active") is True
        or patch.get("license_status") in APPROVED_LICENSE_STATUSES
    ):
        raise HTTPException(
            status_code=409,
            detail="Changing a terms URL invalidates prior approval; submit the new terms first, then approve and activate in separate requests.",
        )
    if terms_changed:
        source.terms_reviewed_at = None
        source.terms_reviewed_by = None
        source.license_status = "unreviewed"
        source.active = False
    if "license_status" in patch and not terms_changed:
        if source.license_status in APPROVED_LICENSE_STATUSES:
            if not source.license_terms_url:
                raise HTTPException(status_code=409, detail="A terms URL is required before approving a source.")
            if not terms_review_rationale or len(terms_review_rationale.strip()) < 20:
                raise HTTPException(status_code=422, detail="A written source-terms review rationale of at least 20 characters is required.")
            source.terms_reviewed_at = datetime.now(timezone.utc)
            source.terms_reviewed_by = principal.identity
        else:
            source.terms_reviewed_at = None
            source.terms_reviewed_by = None

    if source.active:
        if (source.license_status not in APPROVED_LICENSE_STATUSES or not source.license_terms_url
                or not source.terms_reviewed_at or not source.terms_reviewed_by):
            raise HTTPException(status_code=409, detail="A source can only be activated after its terms are documented and reviewed.")
        if not source.retention_policy:
            raise HTTPException(status_code=409, detail="Set a retention policy before activating a source.")

    invalidated_events = _invalidate_unsupported_events(db, source, principal.identity, principal.issuer)
    db.add(AuditLog(
        actor_id=principal.identity, action="source_configuration_changed",
        subject_type="source", subject_id=str(source.id),
        detail={
            "before": before,
            "after": {
                "active": source.active, "license_status": source.license_status,
                "license_terms_url": source.license_terms_url, "retention_policy": source.retention_policy,
                "terms_reviewed_at": source.terms_reviewed_at.isoformat() if source.terms_reviewed_at else None,
            },
            "invalidated_event_count": invalidated_events, "issuer": principal.issuer,
            "terms_review_rationale": terms_review_rationale,
        },
    ))
    db.commit()
    db.refresh(source)
    return _source_dict(source)
