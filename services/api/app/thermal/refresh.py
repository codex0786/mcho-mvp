"""Pull NASA FIRMS detections into PostGIS on a throttled schedule.

There is no background worker on the free hosting tier, so the API triggers a
refresh itself when data is stale (see app/routers/thermal.py), and a scheduled
GitHub workflow requests the API hourly. A transaction-level advisory lock plus
the refresh log ensure only one refresh is claimed per interval.
"""
import json
import logging
import threading
from datetime import datetime, timedelta

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import ThermalDetection, ThermalRefresh, utcnow
from app.thermal.firms import FirmsError, build_area_url, fetch_csv, parse_csv

logger = logging.getLogger("mcho.thermal")

REFRESH_LOCK_KEY = 4_216_001  # arbitrary, unique to this job
RETRY_AFTER_FAILURE = timedelta(minutes=10)
BACKFILL_IF_OLDER_THAN = timedelta(days=3)
INSERT_BATCH = 2_000
_process_lock = threading.Lock()

_INSERT_SQL = text("""
    INSERT INTO thermal_detections (
        id, product, satellite, instrument, acquired_at, latitude, longitude, geometry,
        country_code, brightness_ti4, brightness_ti5, frp, scan, track, confidence,
        daynight, version, ingested_at
    )
    SELECT gen_random_uuid(), r.product, r.satellite, r.instrument, r.acquired_at, r.latitude,
           r.longitude, ST_SetSRID(ST_MakePoint(r.longitude, r.latitude), 4326), cb.iso_a3,
           r.brightness_ti4, r.brightness_ti5, r.frp, r.scan, r.track, r.confidence,
           r.daynight, r.version, now()
    FROM json_to_recordset(CAST(:rows AS json)) AS r(
        product text, satellite text, instrument text, acquired_at timestamptz,
        latitude double precision, longitude double precision, brightness_ti4 double precision,
        brightness_ti5 double precision, frp double precision, scan double precision,
        track double precision, confidence text, daynight text, version text
    )
    JOIN country_boundaries AS cb
      ON ST_Intersects(cb.geometry, ST_SetSRID(ST_MakePoint(r.longitude, r.latitude), 4326))
    ON CONFLICT ON CONSTRAINT uq_thermal_detection_observation DO NOTHING
""")


def configured() -> bool:
    return bool(settings.nasa_firms_api_key.strip())


def products() -> list[str]:
    return [item.strip() for item in settings.firms_products.split(",") if item.strip()]


def last_success(db: Session) -> ThermalRefresh | None:
    return db.scalar(
        select(ThermalRefresh).where(ThermalRefresh.status == "succeeded")
        .order_by(ThermalRefresh.finished_at.desc()).limit(1)
    )


def needs_refresh(db: Session, now: datetime | None = None) -> bool:
    """Stale data and no attempt within the retry window."""
    if not configured():
        return False
    now = now or utcnow()
    success = last_success(db)
    if success and success.finished_at and success.finished_at > now - timedelta(minutes=settings.firms_refresh_minutes):
        return False
    latest_attempt = db.scalar(select(func.max(ThermalRefresh.started_at)))
    return not (latest_attempt and latest_attempt > now - RETRY_AFTER_FAILURE)


def _claim(db: Session, now: datetime) -> ThermalRefresh | None:
    """Atomically decide whether this caller runs the refresh."""
    locked = db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": REFRESH_LOCK_KEY})
    if not locked or not needs_refresh(db, now):
        db.rollback()
        return None
    refresh = ThermalRefresh(started_at=now, status="running")
    db.add(refresh)
    db.commit()
    return refresh


def _requests(db: Session, now: datetime) -> list[tuple[str, int, object]]:
    """(product, day_range, start date or None) for this refresh."""
    latest = db.scalar(select(func.max(ThermalDetection.acquired_at)))
    backfill = latest is None or latest < now - BACKFILL_IF_OLDER_THAN
    plan = []
    for product in products():
        if backfill:
            # Two 5-day windows give ~10 days: the 24 h window plus a 7-day baseline.
            plan.append((product, 5, (now - timedelta(days=9)).date()))
            plan.append((product, 5, None))
        else:
            plan.append((product, 2, None))
    return plan


def refresh_thermal(db: Session, client: httpx.Client, now: datetime | None = None) -> ThermalRefresh | None:
    """Run one refresh if due. Returns the refresh record, or None if not claimed."""
    now = now or utcnow()
    refresh = _claim(db, now)
    if refresh is None:
        return None
    received = rejected = 0
    rows: list[dict] = []
    try:
        for product, day_range, start in _requests(db, now):
            url = build_area_url(settings.nasa_firms_api_key.strip(), product, settings.firms_area, day_range, start)
            parsed, bad = parse_csv(fetch_csv(client, url), product)
            rows.extend(parsed)
            received += len(parsed)
            rejected += bad
        stored = 0
        for offset in range(0, len(rows), INSERT_BATCH):
            result = db.execute(_INSERT_SQL, {"rows": json.dumps(rows[offset:offset + INSERT_BATCH])})
            stored += max(result.rowcount or 0, 0)
        db.execute(
            text("DELETE FROM thermal_detections WHERE acquired_at < :cutoff"),
            {"cutoff": now - timedelta(days=settings.firms_retention_days)},
        )
        db.execute(text("DELETE FROM thermal_refreshes WHERE started_at < :cutoff"), {"cutoff": now - timedelta(days=30)})
        refresh = db.merge(refresh)
        refresh.status = "succeeded"
        refresh.rows_received = received
        refresh.rows_stored = stored
        refresh.error_summary = f"{rejected} malformed rows withheld." if rejected else None
        refresh.finished_at = utcnow()
        db.commit()
        logger.info("thermal_refresh_succeeded received=%s stored=%s rejected=%s", received, stored, rejected)
    except Exception as exc:  # recorded and re-raised for the caller's logs
        db.rollback()
        refresh = db.merge(refresh)
        refresh.status = "failed"
        refresh.error_summary = str(exc) if isinstance(exc, FirmsError) else f"{type(exc).__name__}: refresh stopped."
        refresh.finished_at = utcnow()
        db.commit()
        logger.warning("thermal_refresh_failed error_type=%s summary=%s", type(exc).__name__, refresh.error_summary)
        if not isinstance(exc, FirmsError):
            raise
    return refresh


def refresh_in_background() -> None:
    """Entry point for FastAPI background tasks; one refresh per process at a time."""
    if not _process_lock.acquire(blocking=False):
        return
    from app.db.session import SessionLocal

    try:
        with SessionLocal() as db, httpx.Client(follow_redirects=False) as client:
            refresh_thermal(db, client)
    except Exception:
        logger.exception("thermal_refresh_crashed")
    finally:
        _process_lock.release()
