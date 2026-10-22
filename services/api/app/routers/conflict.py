"""Public, read-only verified conflict events (UCDP Candidate) and their heat cross-checks."""
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.conflict import ucdp
from app.conflict.analysis import conflict_overview
from app.db.session import get_db
from app.models.entities import UcdpRefresh
from app.thermal.analysis import country_exists

router = APIRouter(prefix="/conflict", tags=["verified conflict events"])


@router.get("/overview")
def overview(
    background: BackgroundTasks,
    country: str | None = Query(default=None, pattern=r"^[A-Z]{3}$", description="Limit to one country"),
    db: Session = Depends(get_db),
):
    if country and not country_exists(db, country):
        raise HTTPException(status_code=404, detail="Country is not covered by MCHO.")
    scheduled = ucdp.needs_refresh(db)
    if scheduled:
        background.add_task(ucdp.refresh_in_background)
    latest = db.scalar(select(UcdpRefresh).order_by(UcdpRefresh.started_at.desc()).limit(1))
    last_success = db.scalar(select(func.max(UcdpRefresh.finished_at)).where(UcdpRefresh.status == "succeeded"))
    payload = conflict_overview(db, datetime.now(timezone.utc), country)
    payload["freshness"] = {
        "refresh_scheduled": scheduled,
        "last_successful_refresh_at": last_success.isoformat() if last_success else None,
        "last_attempt": None if latest is None else {"status": latest.status, "started_at": latest.started_at.isoformat(),
                                                     "error_summary": latest.error_summary, "heat_checked": latest.heat_checked,
                                                     "heat_requests": latest.heat_requests,
                                                     "heat_detections_fetched": latest.heat_detections_fetched},
    }
    return payload
