from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.entities import Event, EventEvidence, SourceDocument, Source, EventRevision, EventStatus, VerificationStatus, AuditLog
from app.schemas.events import EventOut, EventPage, CorrectionIn
from app.core.security import require_reviewer

router = APIRouter(prefix="", tags=["events"])


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
def correct_event(event_id: UUID, body: CorrectionIn, reviewer: str = Depends(require_reviewer), db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event or event.is_synthetic:
        raise HTTPException(status_code=404, detail="Event not found.")
    latest = db.scalar(select(func.max(EventRevision.revision_number)).where(EventRevision.event_id == event_id)) or 0
    snapshot = {"event_type": event.event_type, "summary": event.summary,
        "verification_status": event.verification_status.value, "status": event.status.value,
        "event_start": event.event_start.isoformat() if event.event_start else None,
        "country_code": event.country_code}
    revision = EventRevision(event_id=event.id, revision_number=latest + 1, snapshot=snapshot,
        changed_by=reviewer, rationale=body.rationale)
    if body.summary is not None:
        event.summary = body.summary
    if body.verification_status is not None:
        event.verification_status = VerificationStatus(body.verification_status)
    event.status = EventStatus.corrected
    db.add(revision)
    db.commit()
    return {"event_id": str(event.id), "revision_number": latest + 1, "status": event.status.value,
        "message": "Correction recorded; event remains unpublished until re-reviewed and republished."}


@router.post("/events/{event_id}/publish", status_code=200)
def publish_event(event_id: UUID, reviewer: str = Depends(require_reviewer), db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event or event.is_synthetic:
        raise HTTPException(status_code=404, detail="Event not found.")
    if event.verification_status not in {VerificationStatus.verified, VerificationStatus.provisional}:
        raise HTTPException(status_code=409, detail="Only verified or explicitly provisional events can be published.")
    evidence_count = db.scalar(select(func.count()).select_from(EventEvidence).where(EventEvidence.event_id == event_id)) or 0
    if evidence_count < 1:
        raise HTTPException(status_code=409, detail="At least one linked source record is required before publication.")
    if event.event_type in {"civilian_casualties", "perpetrator_attribution", "mass_casualty", "blockade_violation"} and event.verification_status != VerificationStatus.verified:
        raise HTTPException(status_code=409, detail="This high-impact event category requires verified status before publication.")
    event.status = EventStatus.published
    db.add(AuditLog(actor_id=reviewer, action="publish_event", subject_type="event", subject_id=str(event.id),
                    detail={"verification_status": event.verification_status.value, "evidence_count": evidence_count}))
    db.commit()
    return {"event_id": str(event.id), "status": event.status.value, "verification_status": event.verification_status.value,
            "evidence_count": evidence_count, "published_by": reviewer}
