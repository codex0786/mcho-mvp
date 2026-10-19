from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.review_policy import apply_review_decision, ensure_independent_reviewer
from app.core.security import Principal, require_reviewer, require_review_queue_access
from app.db.session import get_db
from app.models.entities import (
    AuditLog, Event, EventEvidence, EventRevision, EventStatus, ReviewDecision, ReviewTask,
    Source, SourceDocument, utcnow,
)
from app.schemas.events import ReviewDecisionIn

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/tasks")
def list_tasks(
    status: str = Query(default="pending", pattern="^(pending|in_review|needs_more_evidence|completed|cancelled)$"),
    reviewer: Principal = Depends(require_review_queue_access),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(ReviewTask).where(ReviewTask.status == status)
        .order_by(ReviewTask.created_at.asc()).limit(200)
    ).all()
    event_ids = [task.subject_id for task in rows if task.subject_type == "event"]
    document_ids = [task.subject_id for task in rows if task.subject_type == "source_document"]
    events_by_id = {
        item.id: item for item in db.scalars(select(Event).where(Event.id.in_(event_ids))).all()
    } if event_ids else {}
    documents_by_id = {}
    if document_ids:
        document_rows = db.execute(
            select(SourceDocument, Source.name)
            .join(Source, SourceDocument.source_id == Source.id)
            .where(SourceDocument.id.in_(document_ids))
        ).all()
        documents_by_id = {document.id: (document, source_name) for document, source_name in document_rows}

    items = []
    for task in rows:
        item = {
            "id": str(task.id), "subject_type": task.subject_type, "subject_id": str(task.subject_id),
            "status": task.status, "priority": task.priority, "created_at": task.created_at.isoformat(),
            "subject_title": None, "canonical_url": None, "source_name": None,
            "event_type": None, "event_status": None, "verification_status": None,
            "country_code": None, "document_review_status": None, "event_summary": None,
        }
        if task.subject_type == "event":
            event = events_by_id.get(task.subject_id)
            if event:
                item.update({
                    "subject_title": event.summary, "event_summary": event.summary,
                    "event_type": event.event_type, "event_status": event.status.value,
                    "verification_status": event.verification_status.value, "country_code": event.country_code,
                })
        elif task.subject_type == "source_document":
            pair = documents_by_id.get(task.subject_id)
            if pair:
                document, source_name = pair
                item.update({
                    "subject_title": document.title, "canonical_url": document.canonical_url,
                    "source_name": source_name, "document_review_status": document.review_status,
                })
        items.append(item)
    return {"items": items, "count": len(items), "limit": 200}


@router.post("/tasks/{task_id}/decisions", status_code=201)
def decide(
    task_id: UUID,
    body: ReviewDecisionIn,
    reviewer: Principal = Depends(require_reviewer),
    db: Session = Depends(get_db),
):
    task = db.get(ReviewTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Review task not found.")
    if task.status not in {"pending", "in_review", "needs_more_evidence"}:
        raise HTTPException(status_code=409, detail="Review task is already closed.")

    event = None
    document = None
    if task.subject_type == "event":
        event = db.get(Event, task.subject_id)
        if event is None:
            raise HTTPException(status_code=409, detail="Review task references a missing event.")
        latest_revision = db.scalar(
            select(EventRevision).where(EventRevision.event_id == event.id)
            .order_by(EventRevision.revision_number.desc()).limit(1)
        )
        if latest_revision is None:
            raise HTTPException(status_code=409, detail="Event has no immutable revision to review.")
        try:
            ensure_independent_reviewer(latest_revision.changed_by, reviewer.identity)
            apply_review_decision(event, body.decision)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    elif task.subject_type == "source_document":
        document = db.get(SourceDocument, task.subject_id)
        if document is None:
            raise HTTPException(status_code=409, detail="Review task references a missing source document.")
        document.review_status = {
            "verify": "approved",
            "accept_provisional": "provisional",
            "dispute": "disputed",
            "reject": "rejected",
            "request_more_evidence": "needs_more_evidence",
        }[body.decision]
        document.reviewed_by = reviewer.identity
        document.reviewed_at = utcnow()
        document.review_rationale = body.rationale

        # Removing approval must immediately remove public events whose remaining
        # evidence no longer meets the publication rules.
        eligible_statuses = {"approved", "public_domain", "open_license", "licensed"}
        linked_events = db.scalars(
            select(Event).join(EventEvidence, EventEvidence.event_id == Event.id)
            .where(EventEvidence.source_document_id == document.id, Event.status == EventStatus.published)
        ).unique().all()
        for linked_event in linked_events:
            valid_count = db.scalar(
                select(func.count()).select_from(EventEvidence)
                .join(SourceDocument, EventEvidence.source_document_id == SourceDocument.id)
                .join(Source, SourceDocument.source_id == Source.id)
                .where(
                    EventEvidence.event_id == linked_event.id,
                    Source.active.is_(True),
                    Source.license_status.in_(eligible_statuses),
                    Source.terms_reviewed_at.is_not(None),
                    Source.terms_reviewed_by.is_not(None),
                    Source.license_terms_url.is_not(None),
                    Source.retention_policy.is_not(None),
                    SourceDocument.review_status == "approved",
                )
            ) or 0
            if valid_count == 0:
                linked_event.status = EventStatus.corrected
                db.add(AuditLog(
                    actor_id=reviewer.identity, action="event_unpublished_invalidated_evidence",
                    subject_type="event", subject_id=str(linked_event.id),
                    detail={
                        "source_document_id": str(document.id), "decision": body.decision,
                        "issuer": reviewer.issuer, "reason": "No approved, permitted evidence remains.",
                    },
                ))
    else:
        raise HTTPException(status_code=409, detail="Unsupported review-task subject type.")

    decision = ReviewDecision(
        task_id=task.id, reviewer_id=reviewer.identity,
        decision=body.decision, rationale=body.rationale,
    )
    task.status = "needs_more_evidence" if body.decision == "request_more_evidence" else "completed"
    db.add_all([
        decision,
        AuditLog(
            actor_id=reviewer.identity, action="review_decision", subject_type=task.subject_type,
            subject_id=str(task.subject_id),
            detail={
                "task_id": str(task.id), "decision": body.decision, "rationale": body.rationale,
                "issuer": reviewer.issuer, "roles": sorted(reviewer.roles),
            },
        ),
    ])
    db.commit()
    return {
        "task_id": str(task.id), "decision": body.decision, "task_status": task.status,
        "event_status": event.status.value if event else None,
        "verification_status": event.verification_status.value if event else None,
        "source_document_review_status": document.review_status if document else None,
        "published": bool(event and event.status.value == "published"),
        "reviewer_subject": reviewer.subject,
    }
