"""Last-year FIRMS archive counts for year-on-year comparison.

For the same calendar days one year earlier, the FIRMS archive is queried per
satellite (standard-processing "SP" products where available, otherwise NRT), and
only daily detection counts per country are stored. A day is recorded as fetched
even when it had no detections, so a stored zero is a real zero and an unfetched
day means "no comparison". Comparisons use only satellites fetched for that day.
"""
import csv
import io
import json
import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import ThermalHistoryFetch, utcnow
from app.thermal.firms import MAX_DAY_RANGE, FirmsError, build_area_url, fetch_csv, parse_csv

logger = logging.getLogger("mcho.thermal.history")

ARCHIVE_FOR = {"VIIRS_SNPP_NRT": "VIIRS_SNPP_SP", "VIIRS_NOAA20_NRT": "VIIRS_NOAA20_SP", "VIIRS_NOAA21_NRT": "VIIRS_NOAA21_SP"}
AVAILABILITY_URL = "https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv"
DAYS_BEFORE = 22  # the 21-day trend plus today
DAYS_AFTER = 2  # a little ahead, so tomorrow's comparison is ready
MAX_REQUESTS_PER_RUN = 6
_MAP_KEY = re.compile(r"^[A-Za-z0-9]{16,64}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_STORE_COUNTS = text("""
    INSERT INTO thermal_history_daily (country_code, day, product, detections)
    SELECT cb.iso_a3, r.day, :product, sum(r.n)
    FROM json_to_recordset(CAST(:rows AS json)) AS r(day date, latitude double precision, longitude double precision, n integer)
    JOIN country_boundaries AS cb
      ON ST_Intersects(cb.geometry, ST_SetSRID(ST_MakePoint(r.longitude, r.latitude), 4326))
    GROUP BY cb.iso_a3, r.day
    ON CONFLICT (country_code, day, product) DO UPDATE SET detections = EXCLUDED.detections
""")
_RECORD_FETCH = text("""
    INSERT INTO thermal_history_fetches (product, day, source_product, rows, fetched_at)
    VALUES (:product, :day, :source, :rows, :fetched_at)
    ON CONFLICT (product, day) DO UPDATE SET source_product = EXCLUDED.source_product,
        rows = EXCLUDED.rows, fetched_at = EXCLUDED.fetched_at
""")


def last_year(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29 February
        return day.replace(year=day.year - 1, day=28)


def availability_url(map_key: str) -> str:
    if not _MAP_KEY.fullmatch(map_key):
        raise FirmsError("The FIRMS MAP_KEY is not in the expected format.")
    return f"{AVAILABILITY_URL}/{map_key}/ALL"


def parse_availability(text_body: str) -> dict[str, tuple[date, date]]:
    """Map product id -> (first, last) available date. Unrecognised rows are ignored."""
    known = set(ARCHIVE_FOR) | set(ARCHIVE_FOR.values())
    ranges: dict[str, tuple[date, date]] = {}
    for row in csv.reader(io.StringIO(text_body)):
        cells = [cell.strip() for cell in row]
        product = next((cell for cell in cells if cell in known), None)
        dates = sorted(date.fromisoformat(cell) for cell in cells if _DATE.fullmatch(cell))
        if product and dates:
            ranges[product] = (dates[0], dates[-1])
    return ranges


def _covers(ranges: dict[str, tuple[date, date]], product: str, day: date) -> bool:
    span = ranges.get(product)
    return bool(span and span[0] <= day <= span[1])


def plan_requests(fetched: set[tuple[str, date]], ranges: dict[str, tuple[date, date]], families: list[str],
                  today: date) -> list[tuple[str, str, date, int]]:
    """(family, source product, start day, day range) chunks still needed, oldest first."""
    wanted = sorted({last_year(today + timedelta(days=offset)) for offset in range(-DAYS_BEFORE, DAYS_AFTER + 1)})
    plan: list[tuple[str, str, date, int]] = []
    for family in families:
        archive = ARCHIVE_FOR.get(family)
        chunk: list[date] = []
        chunk_source: str | None = None
        for day in wanted:
            source = archive if archive and _covers(ranges, archive, day) else (family if _covers(ranges, family, day) else None)
            needed = source is not None and (family, day) not in fetched
            contiguous = chunk and day == chunk[-1] + timedelta(days=1) and source == chunk_source and len(chunk) < MAX_DAY_RANGE
            if chunk and not (needed and contiguous):
                plan.append((family, chunk_source or family, chunk[0], len(chunk)))
                chunk = []
            if needed:
                chunk, chunk_source = (chunk + [day], source) if chunk else ([day], source)
        if chunk:
            plan.append((family, chunk_source or family, chunk[0], len(chunk)))
    return plan


def compact_points(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Count detections per day and ~1 km cell so the country join stays small."""
    counts = Counter((row["acquired_at"][:10], round(row["latitude"], 2), round(row["longitude"], 2)) for row in rows)
    return [{"day": day, "latitude": lat, "longitude": lon, "n": n} for (day, lat, lon), n in counts.items()]


def refresh_history(db: Session, client: httpx.Client, now: datetime | None = None) -> dict[str, Any]:
    """Fetch a few missing archive chunks. Never raises for FIRMS errors; returns a summary."""
    key = settings.nasa_firms_api_key.strip()
    if not key:
        return {"status": "not_configured"}
    now = now or utcnow()
    families = [p for p in (item.strip() for item in settings.firms_products.split(",")) if p in ARCHIVE_FOR]
    try:
        ranges = parse_availability(fetch_csv_any(client, availability_url(key)))
    except FirmsError as exc:
        logger.warning("thermal_history_availability_failed summary=%s", exc)
        return {"status": "failed", "error": str(exc)}
    if not ranges:
        # Without availability we cannot tell a real zero from a missing archive day.
        logger.warning("thermal_history_skipped reason=availability_unparsed")
        return {"status": "skipped", "error": "Archive availability could not be determined."}

    wanted_days = [last_year(now.date() + timedelta(days=offset)) for offset in range(-DAYS_BEFORE, DAYS_AFTER + 1)]
    fetched = set(db.execute(
        select(ThermalHistoryFetch.product, ThermalHistoryFetch.day).where(ThermalHistoryFetch.day.in_(wanted_days))
    ).all())
    plan = plan_requests(fetched, ranges, families, now.date())
    done = 0
    for family, source, start, day_range in plan[:MAX_REQUESTS_PER_RUN]:
        try:
            rows, _rejected = parse_csv(fetch_csv(client, build_area_url(key, source, settings.firms_area, day_range, start)), source)
        except FirmsError as exc:
            logger.warning("thermal_history_fetch_failed product=%s start=%s summary=%s", source, start, exc)
            return {"status": "failed", "requests": done, "remaining": len(plan) - done, "error": str(exc)}
        compacted = compact_points(rows)
        if compacted:
            db.execute(_STORE_COUNTS, {"product": family, "rows": json.dumps(compacted)})
        per_day = Counter(row["acquired_at"][:10] for row in rows)
        for offset in range(day_range):
            day = start + timedelta(days=offset)
            db.execute(_RECORD_FETCH, {"product": family, "day": day, "source": source,
                                       "rows": per_day.get(day.isoformat(), 0), "fetched_at": utcnow()})
        db.commit()
        done += 1
    remaining = max(len(plan) - done, 0)
    logger.info("thermal_history_refreshed requests=%s remaining=%s", done, remaining)
    return {"status": "succeeded", "requests": done, "remaining": remaining}


def fetch_csv_any(client: httpx.Client, url: str) -> str:
    """GET a FIRMS CSV that does not start with detection columns (e.g. availability)."""
    try:
        response = client.get(url, timeout=httpx.Timeout(30.0, connect=10.0))
    except httpx.HTTPError as exc:
        raise FirmsError(f"FIRMS request failed ({type(exc).__name__}).") from None
    if response.status_code != 200:
        raise FirmsError(f"FIRMS returned HTTP {response.status_code}.")
    if "," not in response.text:
        raise FirmsError("FIRMS returned an unexpected response; check that the MAP_KEY is valid.")
    return response.text
