from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.security import require_reviewer
from app.db.session import get_db
from app.models.entities import ReviewTask, ReviewDecision, AuditLog
from app.schemas.events import ReviewDecisionIn

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/tasks")
def list_tasks(status: str = Query(default="pending"), reviewer: str = Depends(require_reviewer), db: Session = Depends(get_db)):
    rows = db.scalars(select(ReviewTask).where(ReviewTask.status == status).order_by(ReviewTask.created_at.asc()).limit(200)).all()
    return {"items": [{"id": str(x.id), "subject_type": x.subject_type, "subject_id": str(x.subject_id),
        "status": x.status, "priority": x.priority, "created_at": x.created_at.isoformat()} for x in rows]}


@router.post("/tasks/{task_id}/decisions", status_code=201)
def decide(task_id: UUID, body: ReviewDecisionIn, reviewer: str = Depends(require_reviewer), db: Session = Depends(get_db)):
    task = db.get(ReviewTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Review task not found.")
    if task.status not in {"pending", "in_review", "needs_more_evidence"}:
        raise HTTPException(status_code=409, detail="Review task is already closed.")
    decision = ReviewDecision(task_id=task.id, reviewer_id=reviewer, decision=body.decision, rationale=body.rationale)
    task.status = "completed" if body.decision != "request_more_evidence" else "needs_more_evidence"
    audit = AuditLog(actor_id=reviewer, action="review_decision", subject_type=task.subject_type,
        subject_id=str(task.subject_id), detail={"task_id": str(task.id), "decision": body.decision})
    db.add_all([decision, audit])
    db.commit()
    return {"task_id": str(task.id), "decision": body.decision, "task_status": task.status}
