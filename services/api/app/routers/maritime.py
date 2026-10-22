"""Public, read-only maritime traffic aggregates from IMF PortWatch."""
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.maritime import portwatch
from app.maritime.analysis import maritime_overview
from app.models.entities import MaritimeRefresh
from app.thermal.analysis import country_exists

router = APIRouter(prefix="/maritime", tags=["maritime aggregates"])


@router.get("/overview")
def overview(
    background: BackgroundTasks,
    country: str | None = Query(default=None, pattern=r"^[A-Z]{3}$", description="Limit ports to one country"),
    db: Session = Depends(get_db),
):
    if country and not country_exists(db, country):
        raise HTTPException(status_code=404, detail="Country is not covered by MCHO.")
    scheduled = portwatch.needs_refresh(db)
    if scheduled:
        background.add_task(portwatch.refresh_in_background)
    latest = db.scalar(select(MaritimeRefresh).order_by(MaritimeRefresh.started_at.desc()).limit(1))
    last_success = db.scalar(select(func.max(MaritimeRefresh.finished_at)).where(MaritimeRefresh.status == "succeeded"))
    payload = maritime_overview(db, datetime.now(timezone.utc), country)
    payload["freshness"] = {
        "refresh_scheduled": scheduled,
        "last_successful_refresh_at": last_success.isoformat() if last_success else None,
        "last_attempt": None if latest is None else {"status": latest.status, "started_at": latest.started_at.isoformat(),
                                                     "error_summary": latest.error_summary},
    }
    return payload
