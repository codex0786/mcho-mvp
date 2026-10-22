"""Public, read-only UN satellite damage assessments (UNOSAT via HDX)."""
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.damage import unosat
from app.damage.analysis import damage_overview
from app.db.session import get_db
from app.models.entities import DamageRefresh
from app.thermal.analysis import country_exists

router = APIRouter(prefix="/damage", tags=["damage assessments"])


@router.get("/overview")
def overview(
    background: BackgroundTasks,
    country: str | None = Query(default=None, pattern=r"^[A-Z]{3}$", description="Limit to one country"),
    db: Session = Depends(get_db),
):
    if country and not country_exists(db, country):
        raise HTTPException(status_code=404, detail="Country is not covered by MCHO.")
    scheduled = unosat.needs_refresh(db)
    if scheduled:
        background.add_task(unosat.refresh_in_background)
    latest = db.scalar(select(DamageRefresh).order_by(DamageRefresh.started_at.desc()).limit(1))
    last_success = db.scalar(select(func.max(DamageRefresh.finished_at)).where(DamageRefresh.status == "succeeded"))
    payload = damage_overview(db, datetime.now(timezone.utc), country)
    payload["freshness"] = {
        "refresh_scheduled": scheduled,
        "last_successful_refresh_at": last_success.isoformat() if last_success else None,
        "last_attempt": None if latest is None else {"status": latest.status, "started_at": latest.started_at.isoformat(),
                                                     "error_summary": latest.error_summary},
    }
    return payload
