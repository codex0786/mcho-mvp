from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.entities import SatelliteScene, MaritimeAggregate, HumanitarianIndicator

router = APIRouter(tags=["observations"])


@router.get("/imagery/scenes")
def list_scenes(from_time: datetime | None = Query(default=None, alias="from"), to_time: datetime | None = Query(default=None, alias="to"), limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    q = select(SatelliteScene)
    if from_time:
        q = q.where(SatelliteScene.acquired_at >= from_time)
    if to_time:
        q = q.where(SatelliteScene.acquired_at < to_time)
    rows = db.scalars(q.order_by(SatelliteScene.acquired_at.desc()).limit(limit)).all()
    return {"items": [{"id": str(x.id), "provider": x.provider, "mission": x.mission,
        "acquired_at": x.acquired_at.isoformat(), "asset_uri": x.asset_uri, "access_status": x.access_status,
        "quality_metadata": x.quality_metadata, "license_note": x.license_note} for x in rows],
        "response_generated_at": datetime.now(timezone.utc).isoformat()}


@router.get("/maritime/aggregates")
def list_maritime(area_id: str | None = None, metric: str | None = None, limit: int = Query(default=200, ge=1, le=1000), db: Session = Depends(get_db)):
    q = select(MaritimeAggregate)
    if area_id:
        q = q.where(MaritimeAggregate.area_id == area_id)
    if metric:
        q = q.where(MaritimeAggregate.metric == metric)
    rows = db.scalars(q.order_by(MaritimeAggregate.period_start.desc()).limit(limit)).all()
    return {"items": [{"id": str(x.id), "area_id": x.area_id, "period_start": x.period_start.isoformat(),
        "period_end": x.period_end.isoformat(), "metric": x.metric, "value": x.value, "unit": x.unit,
        "coverage_fraction": x.coverage_fraction, "source_version": x.source_version, "quality_flags": x.quality_flags}
        for x in rows], "response_generated_at": datetime.now(timezone.utc).isoformat()}


@router.get("/humanitarian/indicators")
def list_humanitarian(indicator_type: str | None = None, geography_id: str | None = None, limit: int = Query(default=200, ge=1, le=1000), db: Session = Depends(get_db)):
    q = select(HumanitarianIndicator)
    if indicator_type:
        q = q.where(HumanitarianIndicator.indicator_type == indicator_type)
    if geography_id:
        q = q.where(HumanitarianIndicator.geography_id == geography_id)
    rows = db.scalars(q.order_by(HumanitarianIndicator.period_start.desc()).limit(limit)).all()
    return {"items": [{"id": str(x.id), "indicator_type": x.indicator_type, "geography_id": x.geography_id,
        "period_start": x.period_start.isoformat(), "period_end": x.period_end.isoformat(), "value": x.value,
        "unit": x.unit, "estimate_status": x.estimate_status, "quality_flags": x.quality_flags}
        for x in rows], "response_generated_at": datetime.now(timezone.utc).isoformat()}
