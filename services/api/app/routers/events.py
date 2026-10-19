from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from geoalchemy2.elements import WKTElement
from app.db.session import get_db
from app.models.entities import (Event, EventEvidence, SourceDocument, Source, EventRevision, EventStatus, VerificationStatus, AuditLog, Claim, ReviewTask, ReviewDecision, utcnow)
from app.schemas.events import EventOut, EventPage, CorrectionIn, EventDraftFromDocumentIn
from app.core.security import Principal, require_publisher, require_roles
from app.core.review_policy import (
    ensure_independent_publisher, ensure_review_after_latest_revision, is_approval_decision,
)

router = APIRouter(prefix="", tags=["events"])
require_analyst = require_roles("analyst", "reviewer", "admin")


@router.post("/events/drafts/from-document/{document_id}", status_code=201)
def create_event_draft_from_document(
    document_id: UUID,
    body: EventDraftFromDocumentIn,
    analyst: Principal = Depends(require_analyst),
    db: Session = Depends(get_db),
):
    """Create an explicitly human-authored, unpublished event draft from reviewed evidence."""
    document = db.get(SourceDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Source document not found.")
    if document.review_status != "approved":
        raise HTTPException(
            status_code=409,
            detail="Only individually approved source documents can be attached to an event draft.",
        )
    source = db.get(Source, document.source_id)
    eligible_license_statuses = {"approved", "public_domain", "open_license", "licensed"}
    if source is None:
        raise HTTPException(status_code=409, detail="Source document references a missing source.")
    if (
        not source.active
        or source.license_status not in eligible_license_statuses
        or source.terms_reviewed_at is None
        or not source.terms_reviewed_by
        or not source.license_terms_url
        or not source.retention_policy
    ):
        raise HTTPException(
            status_code=409,
            detail="Source must be active with reviewed use terms and a retention policy.",
        )

    event = Event(
        event_type=body.event_type,
        summary=body.summary.strip(),
        event_start=body.event_start,
        event_end=body.event_end,
        country_code=body.country_code,
        status=EventStatus.pending_review,
        verification_status=VerificationStatus.unverified,
        attribution_status="unknown",
        confidence_label="unassessed",
        spatial_uncertainty_m=body.spatial_uncertainty_m,
        is_synthetic=False,
    )
    if body.latitude is not None and body.longitude is not None:
        event.geometry = WKTElement(f"POINT({body.longitude} {body.latitude})", srid=4326)

    db.add(event)
    db.flush()
    db.add_all([
        Claim(
            event_id=event.id,
            claim_text=body.summary.strip(),
            claim_type="reported_claim",
            attribution_status="unknown",
        ),
        EventEvidence(
            event_id=event.id,
            source_document_id=document.id,
            relationship="supports",
            note="Analyst linked this reviewed source document as supporting evidence.",
        ),
        EventRevision(
            event_id=event.id,
            revision_number=1,
            snapshot={
                "event_type": body.event_type,
                "summary": body.summary.strip(),
                "event_start": body.event_start.isoformat() if body.event_start else None,
                "event_end": body.event_end.isoformat() if body.event_end else None,
                "country_code": body.country_code,
                "latitude": body.latitude,
                "longitude": body.longitude,
                "spatial_uncertainty_m": body.spatial_uncertainty_m,
                "source_document_id": str(document.id),
                "status": EventStatus.pending_review.value,
                "verification_status": VerificationStatus.unverified.value,
                "attribution_status": "unknown",
            },
            changed_by=analyst.identity,
            rationale=body.rationale,
            changed_at=utcnow(),
        ),
        ReviewTask(
            subject_type="event",
            subject_id=event.id,
            status="pending",
            priority="high" if body.event_type in {
                "civilian_casualties", "mass_casualty", "perpetrator_attribution", "blockade_violation"
            } else "normal",
        ),
        AuditLog(
            actor_id=analyst.identity,
            action="create_event_draft_from_source_document",
            subject_type="event",
            subject_id=str(event.id),
            detail={
                "source_document_id": str(document.id),
                "source_id": str(source.id),
                "rationale": body.rationale,
                "issuer": analyst.issuer,
                "roles": sorted(analyst.roles),
                "status": EventStatus.pending_review.value,
                "auto_publish": False,
            },
        ),
    ])
    db.commit()
    db.refresh(event)
    return {
        "event_id": str(event.id),
        "source_document_id": str(document.id),
        "review_status": "pending_review",
        "verification_status": event.verification_status.value,
        "event_status": event.status.value,
        "published": False,
        "message": "Human-authored draft created. An independent review and separate publication action are required.",
    }


@router.get("/events", response_model=EventPage)
def list_events(
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    event_type: str | None = None,
    verification_status: VerificationStatus | None = None,
    page_size: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
    db: Session = Depends(get_db),
):
    if from_time and to_time and from_time >= to_time:
        raise HTTPException(status_code=400, detail="'from' must be earlier than 'to'.")
    query = select(Event).where(Event.status == EventStatus.published, Event.is_synthetic.is_(False))
    if from_time:
        query = query.where(Event.event_start >= from_time)
    if to_time:
        query = query.where(Event.event_start < to_time)
    if country_code:
        query = query.where(Event.country_code == country_code.upper())
    if event_type:
        query = query.where(Event.event_type == event_type)
    if verification_status:
        query = query.where(Event.verification_status == verification_status)
    total_query = select(func.count()).select_from(query.subquery())
    total = db.scalar(total_query) or 0
    rows = db.scalars(query.order_by(Event.event_start.desc().nullslast(), Event.created_at.desc()).offset(offset).limit(page_size)).all()
    next_cursor = str(offset + page_size) if offset + page_size < total else None
    return EventPage(items=rows, next_cursor=next_cursor, response_generated_at=datetime.now(timezone.utc))


@router.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: UUID, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event or event.status != EventStatus.published or event.is_synthetic:
        raise HTTPException(status_code=404, detail="Published event not found.")
    return event


@router.get("/events/{event_id}/evidence")
def get_event_evidence(event_id: UUID, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event or event.status != EventStatus.published or event.is_synthetic:
        raise HTTPException(status_code=404, detail="Published event not found.")
    rows = db.execute(
        select(EventEvidence, SourceDocument, Source)
        .join(SourceDocument, EventEvidence.source_document_id == SourceDocument.id)
        .join(Source, SourceDocument.source_id == Source.id)
        .where(EventEvidence.event_id == event_id)
    ).all()
    return {"event_id": str(event_id), "items": [
        {"evidence_id": str(link.id), "relationship": link.relationship, "note": link.note,
         "source": source.name, "title": doc.title, "url": doc.canonical_url,
         "published_at": doc.published_at, "retrieved_at": doc.retrieved_at,
         "content_hash": doc.content_hash}
        for link, doc, source in rows
    ]}


@router.get("/map/events")
def map_events(
    west: float = Query(ge=-180, le=180), south: float = Query(ge=-90, le=90),
    east: float = Query(ge=-180, le=180), north: float = Query(ge=-90, le=90),
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    verification_status: VerificationStatus | None = None,
    db: Session = Depends(get_db),
):
    if south >= north or west >= east:
        raise HTTPException(status_code=400, detail="Invalid bbox; antimeridian-crossing boxes are not supported in v1.")
    if from_time and to_time and from_time >= to_time:
        raise HTTPException(status_code=400, detail="'from' must be earlier than 'to'.")
    # Spatial filtering is performed in PostGIS. ST_AsGeoJSON avoids exposing DB-specific geometry objects.
    query = select(Event, func.ST_AsGeoJSON(Event.geometry)).where(
        Event.status == EventStatus.published,
        Event.is_synthetic.is_(False),
        Event.geometry.is_not(None),
        func.ST_Intersects(Event.geometry, func.ST_MakeEnvelope(west, south, east, north, 4326)),
    )
    if from_time:
        query = query.where(Event.event_start >= from_time)
    if to_time:
        query = query.where(Event.event_start < to_time)
    if verification_status:
        query = query.where(Event.verification_status == verification_status)
    # Render a representative point for mixed geometry types so MapLibre clustering remains valid.
    query = query.with_only_columns(Event, func.ST_AsGeoJSON(func.ST_PointOnSurface(Event.geometry)))
    rows = db.execute(query.limit(2000)).all()
    features = []
    for event, geometry_json in rows:
        features.append({"type": "Feature", "id": str(event.id), "geometry": __import__("json").loads(geometry_json),
            "properties": {"event_id": str(event.id), "event_type": event.event_type,
                "verification_status": event.verification_status.value, "event_start": event.event_start.isoformat() if event.event_start else None,
                "confidence_label": event.confidence_label, "spatial_uncertainty_m": event.spatial_uncertainty_m}})
    return {"type": "FeatureCollection", "features": features, "response_generated_at": datetime.now(timezone.utc).isoformat()}


@router.post("/events/{event_id}/corrections", status_code=201)
def correct_event(
    event_id: UUID,
    body: CorrectionIn,
    reviewer: Principal = Depends(require_publisher),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if not event or event.is_synthetic:
        raise HTTPException(status_code=404, detail="Event not found.")
    if event.status == EventStatus.withdrawn:
        raise HTTPException(status_code=409, detail="Withdrawn events cannot be corrected through this endpoint.")

    latest_number = db.scalar(
        select(func.max(EventRevision.revision_number)).where(EventRevision.event_id == event_id)
    ) or 0
    if latest_number < 1:
        raise HTTPException(status_code=409, detail="Event has no revision history to correct.")
    snapshot = {
        "event_type": event.event_type,
        "summary": event.summary,
        "verification_status": event.verification_status.value,
        "status": event.status.value,
        "event_start": event.event_start.isoformat() if event.event_start else None,
        "event_end": event.event_end.isoformat() if event.event_end else None,
        "country_code": event.country_code,
        "confidence_label": event.confidence_label,
        "spatial_uncertainty_m": event.spatial_uncertainty_m,
    }
    revision = EventRevision(
        event_id=event.id,
        revision_number=latest_number + 1,
        snapshot=snapshot,
        changed_by=reviewer.identity,
        rationale=body.rationale,
    )
    if body.summary is not None:
        event.summary = body.summary.strip()
    # A correction must return to independent review; a publisher cannot self-assert
    # verified/provisional status in the correction payload.
    event.verification_status = VerificationStatus.unverified
    event.status = EventStatus.corrected
    db.add(revision)

    active_task_id = db.scalar(
        select(ReviewTask.id).where(
            ReviewTask.subject_type == "event",
            ReviewTask.subject_id == event.id,
            ReviewTask.status.in_(["pending", "in_review", "needs_more_evidence"]),
        ).limit(1)
    )
    if active_task_id is None:
        db.add(ReviewTask(
            subject_type="event",
            subject_id=event.id,
            status="pending",
            priority="high" if event.event_type in {
                "civilian_casualties", "mass_casualty", "perpetrator_attribution", "blockade_violation"
            } else "normal",
        ))
    db.add(AuditLog(
        actor_id=reviewer.identity,
        action="correct_event",
        subject_type="event",
        subject_id=str(event.id),
        detail={
            "revision_number": latest_number + 1,
            "rationale": body.rationale,
            "issuer": reviewer.issuer,
            "review_reopened": active_task_id is None,
        },
    ))
    db.commit()
    return {
        "event_id": str(event.id),
        "revision_number": latest_number + 1,
        "status": event.status.value,
        "verification_status": event.verification_status.value,
        "review_reopened": active_task_id is None,
        "message": "Correction recorded as a new immutable revision; the event is unpublished until it is independently re-reviewed and separately republished.",
    }


@router.post("/events/{event_id}/publish", status_code=200)
def publish_event(
    event_id: UUID,
    reviewer: Principal = Depends(require_publisher),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if not event or event.is_synthetic:
        raise HTTPException(status_code=404, detail="Event not found.")
    if event.status == EventStatus.published:
        raise HTTPException(status_code=409, detail="Event is already published; create a correction revision before republishing.")
    if event.status == EventStatus.withdrawn:
        raise HTTPException(status_code=409, detail="Withdrawn events cannot be republished through this endpoint.")
    if event.status not in {EventStatus.pending_review, EventStatus.corrected}:
        raise HTTPException(status_code=409, detail="Only events in the review workflow can be published.")

    latest_revision = db.scalar(
        select(EventRevision).where(EventRevision.event_id == event_id)
        .order_by(EventRevision.revision_number.desc()).limit(1)
    )
    if latest_revision is None:
        raise HTTPException(status_code=409, detail="Publication requires an immutable event revision.")

    open_task_id = db.scalar(
        select(ReviewTask.id).where(
            ReviewTask.subject_type == "event",
            ReviewTask.subject_id == event.id,
            ReviewTask.status.in_(["pending", "in_review", "needs_more_evidence"]),
        ).limit(1)
    )
    if open_task_id is not None:
        raise HTTPException(status_code=409, detail="An event review task is still open; complete independent review before publishing.")

    latest_review_row = db.execute(
        select(ReviewDecision, ReviewTask)
        .join(ReviewTask, ReviewDecision.task_id == ReviewTask.id)
        .where(ReviewTask.subject_type == "event", ReviewTask.subject_id == event_id)
        .order_by(ReviewDecision.created_at.desc(), ReviewDecision.id.desc())
        .limit(1)
    ).first()
    if latest_review_row is None:
        raise HTTPException(status_code=409, detail="Publication requires an independent review decision.")
    latest_decision, latest_task = latest_review_row
    if latest_task.status != "completed" or not is_approval_decision(latest_decision.decision):
        raise HTTPException(status_code=409, detail="The latest review decision does not approve this event for publication.")
    try:
        ensure_review_after_latest_revision(latest_revision.changed_at, latest_decision.created_at)
        ensure_independent_publisher(
            latest_revision.changed_by,
            latest_decision.reviewer_id,
            reviewer.identity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    expected_verification = {
        "verify": VerificationStatus.verified,
        "accept_provisional": VerificationStatus.provisional,
    }[latest_decision.decision]
    if event.verification_status != expected_verification:
        raise HTTPException(status_code=409, detail="Event verification status does not match the latest review decision.")
    if event.verification_status not in {VerificationStatus.verified, VerificationStatus.provisional}:
        raise HTTPException(status_code=409, detail="Only verified or explicitly provisional events can be published.")

    eligible_license_statuses = {"approved", "public_domain", "open_license", "licensed"}
    evidence_rows = db.execute(
        select(
            EventEvidence.id, Source.active, Source.license_status, Source.terms_reviewed_at,
            Source.terms_reviewed_by, Source.license_terms_url, Source.retention_policy,
            SourceDocument.review_status,
        )
        .join(SourceDocument, EventEvidence.source_document_id == SourceDocument.id)
        .join(Source, SourceDocument.source_id == Source.id)
        .where(EventEvidence.event_id == event_id)
    ).all()
    evidence_count = len(evidence_rows)
    if evidence_count < 1:
        raise HTTPException(status_code=409, detail="At least one linked source record is required before publication.")
    eligible_evidence_count = sum(
        1 for _, active, license_status, terms_reviewed_at, terms_reviewed_by,
        license_terms_url, retention_policy, document_review_status in evidence_rows
        if active and license_status in eligible_license_statuses and terms_reviewed_at is not None
        and terms_reviewed_by and license_terms_url and retention_policy and document_review_status == "approved"
    )
    if eligible_evidence_count < 1:
        raise HTTPException(
            status_code=409,
            detail="Publication requires an active permitted source and an individually approved source document.",
        )
    high_impact_types = {"civilian_casualties", "perpetrator_attribution", "mass_casualty", "blockade_violation"}
    if event.event_type in high_impact_types and event.verification_status != VerificationStatus.verified:
        raise HTTPException(status_code=409, detail="This high-impact event category requires verified status before publication.")

    event.status = EventStatus.published
    db.add(AuditLog(
        actor_id=reviewer.identity,
        action="publish_event",
        subject_type="event",
        subject_id=str(event.id),
        detail={
            "revision_number": latest_revision.revision_number,
            "review_decision_id": str(latest_decision.id),
            "reviewer_id": latest_decision.reviewer_id,
            "verification_status": event.verification_status.value,
            "evidence_count": evidence_count,
            "eligible_evidence_count": eligible_evidence_count,
            "publisher_id": reviewer.identity,
            "issuer": reviewer.issuer,
        },
    ))
    db.commit()
    return {
        "event_id": str(event.id),
        "status": event.status.value,
        "verification_status": event.verification_status.value,
        "revision_number": latest_revision.revision_number,
        "review_decision_id": str(latest_decision.id),
        "evidence_count": evidence_count,
        "eligible_evidence_count": eligible_evidence_count,
        "published_by": reviewer.subject,
    }
