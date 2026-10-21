"""Public, read-only satellite heat detections and derived insights.

NASA FIRMS data is public and attributed; these endpoints label every record as
an unverified observation. Nothing here creates or publishes events.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import ThermalRefresh
from app.thermal import refresh as thermal_refresh
from app.thermal.analysis import country_exists, country_list, country_trend, detections_geojson, insights

router = APIRouter(prefix="/thermal", tags=["satellite thermal detections"])
COUNTRY_PATTERN = r"^[A-Z]{3}$"


def _known_country(db: Session, country: str | None) -> str | None:
    if country and not country_exists(db, country):
        raise HTTPException(status_code=404, detail="Country is not covered by MCHO.")
    return country


def _freshness(db: Session, background: BackgroundTasks) -> dict:
    configured = thermal_refresh.configured()
    scheduled = False
    if configured and thermal_refresh.needs_refresh(db):
        background.add_task(thermal_refresh.refresh_in_background)
        scheduled = True
    success = thermal_refresh.last_success(db)
    latest = db.scalar(select(ThermalRefresh).order_by(ThermalRefresh.started_at.desc()).limit(1))
    return {
        "configured": configured,
        "refresh_scheduled": scheduled,
        "refresh_running": bool(latest and latest.status == "running"),
        "last_successful_refresh_at": success.finished_at.isoformat() if success and success.finished_at else None,
        "last_attempt": None if latest is None else {
            "status": latest.status, "started_at": latest.started_at.isoformat(),
            "error_summary": latest.error_summary,
        },
    }


@router.get("/detections")
def thermal_detections(
    background: BackgroundTasks,
    west: float = Query(ge=-180, le=180), south: float = Query(ge=-90, le=90),
    east: float = Query(ge=-180, le=180), north: float = Query(ge=-90, le=90),
    hours: int = Query(default=24, ge=1, le=72),
    country: str | None = Query(default=None, pattern=COUNTRY_PATTERN, description="ISO 3166-1 alpha-3 code"),
    db: Session = Depends(get_db),
):
    if south >= north or west >= east:
        raise HTTPException(status_code=400, detail="Invalid bbox; antimeridian-crossing boxes are not supported.")
    now = datetime.now(timezone.utc)
    payload = detections_geojson(db, now, hours, (west, south, east, north), _known_country(db, country))
    payload["freshness"] = _freshness(db, background)
    payload["response_generated_at"] = now.isoformat()
    return payload


@router.get("/insights")
def thermal_insights(
    background: BackgroundTasks,
    hours: int = Query(default=24, ge=6, le=72),
    country: str | None = Query(default=None, pattern=COUNTRY_PATTERN, description="Limit clusters to one country"),
    db: Session = Depends(get_db),
):
    payload = insights(db, datetime.now(timezone.utc), hours, _known_country(db, country))
    payload["freshness"] = _freshness(db, background)
    return payload


@router.get("/countries")
def thermal_countries(db: Session = Depends(get_db)):
    """Countries MCHO covers, with bounding boxes for map navigation."""
    return {"items": country_list(db)}


@router.get("/countries/{iso_a3}/trend")
def thermal_country_trend(
    background: BackgroundTasks,
    iso_a3: str = Path(pattern=COUNTRY_PATTERN),
    days: int = Query(default=21, ge=7, le=21),
    db: Session = Depends(get_db),
):
    payload = country_trend(db, datetime.now(timezone.utc), _known_country(db, iso_a3), days)
    payload["freshness"] = _freshness(db, background)
    return payload
