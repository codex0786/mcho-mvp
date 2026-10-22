"""UCDP Candidate events: verified, preliminary data on lethal organised violence.

Source: Uppsala Conflict Data Program (UCDP), Candidate Events Dataset, public
monthly CSV releases at https://ucdp.uu.se/downloads/ (CC BY 4.0). Cite:
Hegre, Croicu, Eck and Högbladh (2020), "Introducing the UCDP Candidate Events
Dataset", Research & Politics, doi:10.1177/2053168020935257.

Each monthly release (version YY.0.M) covers events in month M, published
around the 20th of the following month. MCHO stores events located in its MENA
countries, keeps UCDP's own figures unchanged (best/low/high deaths, type of
violence, actors, precision codes), and records which releases were fetched so
a month that was not downloaded is never shown as a month without violence.
"""
import csv
import io
import json
import logging
import threading
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.entities import UcdpRefresh, UcdpRelease, utcnow

logger = logging.getLogger("mcho.ucdp")

BASE_URL = "https://ucdp.uu.se/downloads/candidateged/"
MONTHS_KEPT = 6  # monthly releases looked for, newest first
RETENTION_DAYS = 400
REFRESH_HOURS = 12
RETRY_AFTER_FAILURE = timedelta(hours=1)
REFRESH_LOCK_KEY = 4_216_004
MAX_BYTES = 40_000_000
REGION = (-18.0, 8.0, 64.0, 40.0)  # west, south, east, north: the FIRMS area
COAST_DEGREES = 0.5  # events at sea are assigned to the nearest country within ~50 km
# UCDP's names for MCHO's countries. An event outside every MENA border is kept only when
# UCDP itself places it in one of these (e.g. off the coast), never one across a land border.
MENA_UCDP_NAMES = frozenset({
    "Algeria", "Bahrain", "Egypt", "Iran", "Iraq", "Israel", "Jordan", "Kuwait", "Lebanon", "Libya", "Mauritania", "Morocco",
    "Oman", "Palestine", "Qatar", "Saudi Arabia", "Sudan", "Syria", "Tunisia", "United Arab Emirates", "Western Sahara",
    "Yemen (North Yemen)", "Yemen",
})
VIOLENCE_TYPES = {1: "State-based conflict", 2: "Non-state conflict", 3: "One-sided violence against civilians"}
ATTRIBUTION = "Source: Uppsala Conflict Data Program (UCDP) Candidate Events Dataset, CC BY 4.0"
CITATION = ("Hegre, Croicu, Eck and Högbladh (2020), \"Introducing the UCDP Candidate Events Dataset\", "
            "Research & Politics, doi:10.1177/2053168020935257")
_process_lock = threading.Lock()


class UcdpError(RuntimeError):
    """A failure with a message safe to store and show."""


def release_for(year: int, month: int) -> str:
    return f"{year % 100}.0.{month}"


def release_url(release: str) -> str:
    return f"{BASE_URL}GEDEvent_v{release.replace('.', '_')}.csv"


def recent_releases(today: date, months: int = MONTHS_KEPT) -> list[str]:
    """Releases for the current and previous months, newest first (the newest may not exist yet)."""
    out, year, month = [], today.year, today.month
    for _ in range(months + 1):
        out.append(release_for(year, month))
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return out


def _int(value: str | None, default: int | None = None) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else default
    except ValueError:
        return default


def parse_events(body: str, release: str) -> tuple[list[dict[str, Any]], int]:
    """Rows inside the region with valid coordinates and dates; returns (rows, total rows read)."""
    west, south, east, north = REGION
    rows, total = [], 0
    for raw in csv.DictReader(io.StringIO(body.lstrip("﻿"))):
        total += 1
        try:
            lat, lon = float(raw["latitude"]), float(raw["longitude"])
            start = date.fromisoformat((raw.get("date_start") or "")[:10])
            end = date.fromisoformat((raw.get("date_end") or "")[:10])
            event_id = int(raw["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (west <= lon <= east and south <= lat <= north) or end < start:
            continue
        violence = _int(raw.get("type_of_violence"))
        if violence not in VIOLENCE_TYPES:
            continue
        rows.append({
            "id": event_id, "relid": (raw.get("relid") or "")[:64], "release": release, "type_of_violence": violence,
            "conflict_name": raw.get("conflict_name") or "", "dyad_name": raw.get("dyad_name") or "",
            "side_a": raw.get("side_a") or "", "side_b": raw.get("side_b") or "",
            "where_description": raw.get("where_description") or None, "adm_1": raw.get("adm_1") or None,
            "ucdp_country": (raw.get("country") or "")[:120], "mena_named": (raw.get("country") or "") in MENA_UCDP_NAMES,
            "latitude": lat, "longitude": lon,
            "date_start": start.isoformat(), "date_end": end.isoformat(),
            "date_prec": _int(raw.get("date_prec"), 5), "where_prec": _int(raw.get("where_prec"), 7),
            "event_clarity": _int(raw.get("event_clarity")), "code_status": (raw.get("code_status") or None),
            "deaths_best": _int(raw.get("best"), 0), "deaths_low": _int(raw.get("low"), 0), "deaths_high": _int(raw.get("high"), 0),
            "deaths_civilians": _int(raw.get("deaths_civilians"), 0), "number_of_sources": _int(raw.get("number_of_sources")),
        })
    return rows, total


# Country by containment, else (for events UCDP places in a MENA country) the nearest border within ~50 km.
# The heat cross-check starts as pending only where UCDP's place and date are precise enough.
_UPSERT_EVENTS = text("""
    WITH r AS (
        SELECT * FROM json_to_recordset(CAST(:rows AS json)) AS r(
            id bigint, relid text, release text, type_of_violence smallint, conflict_name text, dyad_name text, side_a text,
            side_b text, where_description text, adm_1 text, ucdp_country text, mena_named boolean, latitude double precision,
            longitude double precision, date_start date, date_end date, date_prec smallint, where_prec smallint,
            event_clarity smallint, code_status text, deaths_best int, deaths_low int, deaths_high int,
            deaths_civilians int, number_of_sources int)
    ), located AS (
        SELECT r.*, ST_SetSRID(ST_MakePoint(r.longitude, r.latitude), 4326) AS geometry,
               coalesce(
                   (SELECT b.iso_a3 FROM country_boundaries AS b
                    WHERE ST_Intersects(b.geometry, ST_SetSRID(ST_MakePoint(r.longitude, r.latitude), 4326)) LIMIT 1),
                   (SELECT b.iso_a3 FROM country_boundaries AS b
                    WHERE r.mena_named AND ST_DWithin(b.geometry, ST_SetSRID(ST_MakePoint(r.longitude, r.latitude), 4326), :coast)
                    ORDER BY ST_Distance(b.geometry, ST_SetSRID(ST_MakePoint(r.longitude, r.latitude), 4326)) LIMIT 1)
               ) AS country_code
        FROM r
    )
    INSERT INTO ucdp_events (id, relid, release, type_of_violence, conflict_name, dyad_name, side_a, side_b, where_description,
        adm_1, ucdp_country, country_code, latitude, longitude, geometry, date_start, date_end, date_prec, where_prec,
        event_clarity, code_status, deaths_best, deaths_low, deaths_high, deaths_civilians, number_of_sources, heat_status, updated_at)
    SELECT id, relid, release, type_of_violence, conflict_name, dyad_name, side_a, side_b, where_description, adm_1, ucdp_country,
        country_code, latitude, longitude, geometry, date_start, date_end, date_prec, where_prec, event_clarity, code_status,
        deaths_best, deaths_low, deaths_high, deaths_civilians, number_of_sources,
        CASE WHEN where_prec <= 2 AND date_prec <= 2 AND date_end - date_start <= 6 THEN 'pending' ELSE 'not_checkable' END, now()
    FROM located WHERE country_code IS NOT NULL
    ON CONFLICT (id) DO UPDATE SET
        relid = EXCLUDED.relid, release = EXCLUDED.release, type_of_violence = EXCLUDED.type_of_violence,
        conflict_name = EXCLUDED.conflict_name, dyad_name = EXCLUDED.dyad_name, side_a = EXCLUDED.side_a, side_b = EXCLUDED.side_b,
        where_description = EXCLUDED.where_description, adm_1 = EXCLUDED.adm_1, ucdp_country = EXCLUDED.ucdp_country,
        country_code = EXCLUDED.country_code, latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude, geometry = EXCLUDED.geometry,
        date_start = EXCLUDED.date_start, date_end = EXCLUDED.date_end, date_prec = EXCLUDED.date_prec, where_prec = EXCLUDED.where_prec,
        event_clarity = EXCLUDED.event_clarity, code_status = EXCLUDED.code_status, deaths_best = EXCLUDED.deaths_best,
        deaths_low = EXCLUDED.deaths_low, deaths_high = EXCLUDED.deaths_high, deaths_civilians = EXCLUDED.deaths_civilians,
        number_of_sources = EXCLUDED.number_of_sources, updated_at = now(),
        -- A revised place or date invalidates an earlier heat cross-check.
        heat_status = CASE
            WHEN ucdp_events.latitude = EXCLUDED.latitude AND ucdp_events.longitude = EXCLUDED.longitude
             AND ucdp_events.date_start = EXCLUDED.date_start AND ucdp_events.date_end = EXCLUDED.date_end
             AND ucdp_events.heat_status <> 'not_checkable' THEN ucdp_events.heat_status
            ELSE EXCLUDED.heat_status END
    RETURNING id
""")


def fetch_release(client: httpx.Client, release: str, known: UcdpRelease | None) -> tuple[str | None, dict[str, str | None]]:
    """Return (body or None if unchanged/not yet published, validators)."""
    headers = {}
    if known and known.etag:
        headers["If-None-Match"] = known.etag
    if known and known.last_modified:
        headers["If-Modified-Since"] = known.last_modified
    try:
        response = client.get(release_url(release), headers=headers, timeout=httpx.Timeout(120.0, connect=10.0))
    except httpx.HTTPError as exc:
        raise UcdpError(f"UCDP request failed ({type(exc).__name__}).") from None
    validators = {"etag": response.headers.get("etag"), "last_modified": response.headers.get("last-modified")}
    if response.status_code in (304, 404):
        return None, validators
    if response.status_code != 200:
        raise UcdpError(f"UCDP returned HTTP {response.status_code} for release {release}.")
    if len(response.content) > MAX_BYTES:
        raise UcdpError(f"UCDP release {release} is larger than expected.")
    body = response.content.decode("utf-8-sig", errors="replace")
    if not body.startswith("id,") and "\nid," not in body[:200] and not body.lstrip().startswith('"id"'):
        raise UcdpError(f"UCDP release {release} is not in the expected CSV format.")
    return body, validators


def needs_refresh(db: Session, now: datetime | None = None) -> bool:
    now = now or utcnow()
    last_success = db.scalar(select(func.max(UcdpRefresh.finished_at)).where(UcdpRefresh.status == "succeeded"))
    pending = db.scalar(text("SELECT count(*) FROM ucdp_events WHERE heat_status = 'pending'"))
    from app.core.config import settings  # heat checks only run with a FIRMS key

    checks_due = bool(pending) and bool(settings.nasa_firms_api_key.strip())
    if last_success and last_success > now - timedelta(hours=REFRESH_HOURS) and not checks_due:
        return False
    last_attempt = db.scalar(select(func.max(UcdpRefresh.started_at)))
    retry = timedelta(minutes=10) if checks_due and last_success and last_success > now - timedelta(hours=REFRESH_HOURS) else RETRY_AFTER_FAILURE
    return not (last_attempt and last_attempt > now - retry)


def sync_releases(db: Session, client: httpx.Client, now: datetime) -> int:
    """Download new or changed monthly releases. Network calls run with no transaction open."""
    stored = 0
    for release in recent_releases(now.date()):
        known = db.get(UcdpRelease, release)
        db.commit()
        body, validators = fetch_release(client, release, known)
        if body is None:
            continue
        rows, total = parse_events(body, release)
        kept = 0
        for offset in range(0, len(rows), 2000):
            kept += len(db.execute(_UPSERT_EVENTS, {"rows": json.dumps(rows[offset:offset + 2000]), "coast": COAST_DEGREES}).all())
        record = known or UcdpRelease(release=release, url=release_url(release))
        record.etag, record.last_modified = validators["etag"], validators["last_modified"]
        record.rows_total, record.rows_mena, record.fetched_at = total, kept, utcnow()
        db.add(record)
        db.commit()
        stored += kept
        logger.info("ucdp_release_stored release=%s rows=%s mena=%s", release, total, kept)
    db.execute(text("DELETE FROM ucdp_events WHERE date_end < :cutoff"), {"cutoff": now.date() - timedelta(days=RETENTION_DAYS)})
    db.commit()
    return stored


def refresh_ucdp(db: Session, client: httpx.Client, firms_client: httpx.Client | None = None,
                 now: datetime | None = None) -> UcdpRefresh | None:
    from app.conflict.heat_match import check_pending_events

    now = now or utcnow()
    wall_start = utcnow()
    if not db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": REFRESH_LOCK_KEY}) or not needs_refresh(db, now):
        db.rollback()
        return None
    refresh = UcdpRefresh(started_at=now, status="running")
    db.add(refresh)
    db.commit()
    refresh_id = refresh.id
    stored = 0
    heat = {"checked": 0, "requests": 0, "fetched": 0}
    try:
        stored = sync_releases(db, client, now)
        heat = check_pending_events(db, firms_client or client, now)
        refresh = db.get(UcdpRefresh, refresh_id)
        refresh.status, refresh.rows_stored, refresh.heat_checked = "succeeded", stored, heat["checked"]
        refresh.heat_requests, refresh.heat_detections_fetched = heat["requests"], heat["fetched"]
        refresh.finished_at = now + (utcnow() - wall_start)
        db.commit()
        logger.info("ucdp_refresh_succeeded rows=%s heat=%s", stored, heat)
    except Exception as exc:
        db.rollback()
        refresh = db.get(UcdpRefresh, refresh_id)
        refresh.status, refresh.rows_stored, refresh.heat_checked = "failed", stored, heat["checked"]
        refresh.error_summary = str(exc) if isinstance(exc, UcdpError) else f"{type(exc).__name__}: refresh stopped."
        refresh.finished_at = now + (utcnow() - wall_start)
        db.commit()
        logger.warning("ucdp_refresh_failed error_type=%s summary=%s", type(exc).__name__, refresh.error_summary)
        if not isinstance(exc, UcdpError):
            raise
    return refresh


def refresh_in_background() -> None:
    if not _process_lock.acquire(blocking=False):
        return
    from app.db.session import SessionLocal

    try:
        with SessionLocal() as db, httpx.Client(follow_redirects=True, headers={"User-Agent": "MCHO observatory (non-commercial)"}) as client:
            refresh_ucdp(db, client)
    except Exception:
        logger.exception("ucdp_refresh_crashed")
    finally:
        _process_lock.release()
