"""IMF PortWatch daily chokepoint transits and port calls (aggregates only).

Source: International Monetary Fund, PortWatch (https://portwatch.imf.org), public
ArcGIS feature services. Licence: IMF terms for Data
(https://www.imf.org/external/terms.htm): reuse permitted with attribution; data
must not be altered, and material transformations must be stated. PortWatch
derives its figures from AIS vessel signals; only IMF's published daily
aggregates are stored here, never vessel-level positions.
"""
import json
import logging
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.entities import MaritimeRefresh, utcnow

logger = logging.getLogger("mcho.maritime")

SERVICE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
CHOKEPOINT_DAILY = f"{SERVICE}/Daily_Chokepoints_Data/FeatureServer/0/query"
CHOKEPOINT_META = f"{SERVICE}/PortWatch_chokepoints_database/FeatureServer/0/query"
PORT_DAILY = f"{SERVICE}/Daily_Ports_Data/FeatureServer/0/query"
PORT_META = f"{SERVICE}/PortWatch_ports/FeatureServer/1/query"
# Suez, Bosporus, Bab el-Mandeb, Hormuz, Cape of Good Hope (Red Sea rerouting), Gibraltar.
CHOKEPOINTS = ("chokepoint1", "chokepoint3", "chokepoint4", "chokepoint6", "chokepoint7", "chokepoint8")
HISTORY_DAYS = 400
REVISION_DAYS = 7
REFRESH_HOURS = 6
RETRY_AFTER_FAILURE = timedelta(minutes=30)
PAGE_SIZE = 1000
WRITE_BATCH = 2000
REFRESH_LOCK_KEY = 4_216_002
SOURCE_VERSION = "IMF PortWatch"
ATTRIBUTION = "Source: International Monetary Fund, PortWatch, https://portwatch.imf.org"

CHOKEPOINT_METRICS = {
    "n_total": ("transits_total", "vessels"), "n_tanker": ("transits_tanker", "vessels"),
    "n_container": ("transits_container", "vessels"), "n_dry_bulk": ("transits_dry_bulk", "vessels"),
    "n_cargo": ("transits_cargo", "vessels"), "capacity": ("capacity_dwt", "tonnes"),
}
PORT_METRICS = {
    "portcalls": ("portcalls_total", "vessels"), "portcalls_tanker": ("portcalls_tanker", "vessels"),
    "portcalls_container": ("portcalls_container", "vessels"), "portcalls_cargo": ("portcalls_cargo", "vessels"),
    "import": ("import_tonnes", "tonnes"), "export": ("export_tonnes", "tonnes"),
}
_process_lock = threading.Lock()

_UPSERT = text("""
    INSERT INTO maritime_aggregates (id, area_id, period_start, period_end, metric, value, unit,
                                     coverage_fraction, source_version, quality_flags, created_at)
    SELECT gen_random_uuid(), r.area_id, r.period_start, r.period_start + interval '1 day', r.metric, r.value, r.unit,
           NULL, :source_version, CAST('["ais_derived"]' AS json), now()
    FROM json_to_recordset(CAST(:rows AS json)) AS r(area_id text, period_start timestamptz, metric text, value double precision, unit text)
    ON CONFLICT ON CONSTRAINT uq_maritime_aggregate_metric
    DO UPDATE SET value = EXCLUDED.value, unit = EXCLUDED.unit, created_at = now()
""")
_UPSERT_AREA = text("""
    INSERT INTO maritime_areas (id, kind, name, country_code, geometry, reference_vessels_per_year, updated_at)
    VALUES (:id, :kind, :name, :country, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :reference, now())
    ON CONFLICT (id) DO UPDATE SET kind = EXCLUDED.kind, name = EXCLUDED.name, country_code = EXCLUDED.country_code,
        geometry = EXCLUDED.geometry, reference_vessels_per_year = EXCLUDED.reference_vessels_per_year, updated_at = now()
""")


class PortWatchError(RuntimeError):
    """A PortWatch failure with a message safe to store and show."""


def query_all(client: httpx.Client, url: str, where: str, out_fields: str, geometry: bool = False) -> list[dict[str, Any]]:
    """Page through an ArcGIS layer query; returns attributes (plus geometry if asked)."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {"where": where, "outFields": out_fields, "f": "json", "resultOffset": offset,
                  "resultRecordCount": PAGE_SIZE, "returnGeometry": str(geometry).lower(), "outSR": 4326,
                  "orderByFields": "ObjectId" if "Daily_" in url else "OBJECTID"}
        try:
            response = client.get(url, params=params, timeout=httpx.Timeout(60.0, connect=10.0))
        except httpx.HTTPError as exc:
            raise PortWatchError(f"PortWatch request failed ({type(exc).__name__}).") from None
        if response.status_code != 200:
            raise PortWatchError(f"PortWatch returned HTTP {response.status_code}.")
        try:
            body = response.json()
        except ValueError:
            raise PortWatchError("PortWatch returned an unexpected response.") from None
        if "error" in body:
            raise PortWatchError(f"PortWatch query error: {str(body['error'].get('message', 'unknown'))[:200]}")
        features = body.get("features") or []
        for feature in features:
            row = dict(feature.get("attributes") or {})
            if geometry and feature.get("geometry"):
                row["_lon"], row["_lat"] = feature["geometry"].get("x"), feature["geometry"].get("y")
            rows.append(row)
        if not body.get("exceededTransferLimit") or not features:
            return rows
        offset += len(features)


def _metric_rows(records: list[dict[str, Any]], metrics: dict[str, tuple[str, str]], allowed: set[str]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        area, day = record.get("portid"), record.get("date")
        if area not in allowed or not isinstance(day, str):
            continue
        try:
            start = datetime.combine(date.fromisoformat(day[:10]), datetime.min.time(), tzinfo=timezone.utc)
        except ValueError:
            continue
        for field, (metric, unit) in metrics.items():
            value = record.get(field)
            if isinstance(value, (int, float)):  # missing values are skipped, never stored as zero
                rows.append({"area_id": area, "period_start": start.isoformat(), "metric": metric, "value": float(value), "unit": unit})
    return rows


def configured_countries(db: Session) -> list[str]:
    return [code for (code,) in db.execute(text("SELECT iso_a3 FROM country_boundaries ORDER BY iso_a3")).all()]


def needs_refresh(db: Session, now: datetime | None = None) -> bool:
    now = now or utcnow()
    last_success = db.scalar(select(func.max(MaritimeRefresh.finished_at)).where(MaritimeRefresh.status == "succeeded"))
    if last_success and last_success > now - timedelta(hours=REFRESH_HOURS):
        return False
    last_attempt = db.scalar(select(func.max(MaritimeRefresh.started_at)))
    return not (last_attempt and last_attempt > now - RETRY_AFTER_FAILURE)


def refresh_maritime(db: Session, client: httpx.Client, now: datetime | None = None) -> MaritimeRefresh | None:
    """Fetch first with no transaction open, then write in short committed batches.

    PortWatch requests can take minutes; holding a database transaction open
    across them lets the database drop an idle-in-transaction connection.
    """
    now = now or utcnow()
    wall_start = utcnow()
    if not db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": REFRESH_LOCK_KEY}) or not needs_refresh(db, now):
        db.rollback()
        return None
    refresh = MaritimeRefresh(started_at=now, status="running")
    db.add(refresh)
    db.commit()
    refresh_id = refresh.id
    try:
        countries = configured_countries(db)
        latest = db.scalar(text("SELECT max(period_start) FROM maritime_aggregates WHERE source_version = :v"), {"v": SOURCE_VERSION})
        db.commit()  # close the read transaction before slow network calls
        since = (latest - timedelta(days=REVISION_DAYS)).date() if latest else (now - timedelta(days=HISTORY_DAYS)).date()
        chokepoint_list = ",".join(f"'{c}'" for c in CHOKEPOINTS)
        country_list = ",".join(f"'{c}'" for c in countries)
        day_filter = f"date >= '{since.isoformat()}'"

        phase = utcnow()
        chokepoints = query_all(client, CHOKEPOINT_META, f"portid IN ({chokepoint_list})", "portid,portname,lat,lon,vessel_count_total", geometry=True)
        ports = query_all(client, PORT_META, f"ISO3 IN ({country_list})", "portid,portname,ISO3,lat,long,vessel_count_total", geometry=True)
        chokepoint_daily = query_all(client, CHOKEPOINT_DAILY, f"portid IN ({chokepoint_list}) AND {day_filter}",
                                     "portid,date," + ",".join(CHOKEPOINT_METRICS))
        port_daily = query_all(client, PORT_DAILY, f"ISO3 IN ({country_list}) AND {day_filter}", "portid,date," + ",".join(PORT_METRICS))
        logger.info("maritime_fetch_done seconds=%.1f chokepoint_days=%s port_days=%s since=%s",
                    (utcnow() - phase).total_seconds(), len(chokepoint_daily), len(port_daily), since)

        rows = _metric_rows(chokepoint_daily, CHOKEPOINT_METRICS, set(CHOKEPOINTS))
        rows += _metric_rows(port_daily, PORT_METRICS, {p["portid"] for p in ports})
        phase = utcnow()
        for c in chokepoints:
            db.execute(_UPSERT_AREA, {"id": c["portid"], "kind": "chokepoint", "name": c["portname"], "country": None,
                                      "lon": c.get("_lon", c.get("lon")), "lat": c.get("_lat", c.get("lat")), "reference": c.get("vessel_count_total")})
        for p in ports:
            db.execute(_UPSERT_AREA, {"id": p["portid"], "kind": "port", "name": p["portname"], "country": p.get("ISO3"),
                                      "lon": p.get("_lon", p.get("long")), "lat": p.get("_lat", p.get("lat")), "reference": p.get("vessel_count_total")})
        db.commit()
        for offset in range(0, len(rows), WRITE_BATCH):
            db.execute(_UPSERT, {"rows": json.dumps(rows[offset:offset + WRITE_BATCH]), "source_version": SOURCE_VERSION})
            db.commit()
        db.execute(text("DELETE FROM maritime_aggregates WHERE source_version = :v AND period_start < :cutoff"),
                   {"v": SOURCE_VERSION, "cutoff": now - timedelta(days=HISTORY_DAYS + 30)})
        refresh = db.get(MaritimeRefresh, refresh_id)
        refresh.status, refresh.rows_stored = "succeeded", len(rows)
        refresh.finished_at = now + (utcnow() - wall_start)
        db.commit()
        logger.info("maritime_refresh_succeeded rows=%s write_seconds=%.1f", len(rows), (utcnow() - phase).total_seconds())
    except Exception as exc:
        db.rollback()
        refresh = db.get(MaritimeRefresh, refresh_id)
        refresh.status = "failed"
        refresh.error_summary = str(exc) if isinstance(exc, PortWatchError) else f"{type(exc).__name__}: refresh stopped."
        refresh.finished_at = now + (utcnow() - wall_start)
        db.commit()
        logger.warning("maritime_refresh_failed error_type=%s summary=%s", type(exc).__name__, refresh.error_summary)
        if not isinstance(exc, PortWatchError):
            raise
    return refresh


def refresh_in_background() -> None:
    if not _process_lock.acquire(blocking=False):
        return
    from app.db.session import SessionLocal

    try:
        with SessionLocal() as db, httpx.Client(follow_redirects=False) as client:
            refresh_maritime(db, client)
    except Exception:
        logger.exception("maritime_refresh_crashed")
    finally:
        _process_lock.release()
