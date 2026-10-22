"""Cross-check UCDP events against NASA FIRMS satellite heat around the event.

For each UCDP event whose place and date are precise (where_prec 1-2,
date_prec 1-2, at most 7 days long), MCHO fetches archived VIIRS detections
around it and records:

- heat within the radius (5 km for an exact location, 25 km for "within ~25 km")
  from the day before date_start to the day after date_end;
- detections at persistent sites (~2 km cells with heat on at least 4 of the 7
  days before that window: flares, industry) are counted separately and not
  treated as a match.

A match means a heat signature was seen near a verified event at about the
same time. It does not prove the event caused the fire, and no heat does not
mean nothing burned (clouds, smoke, timing, small fires).
"""
import logging
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.thermal.analysis import BASELINE_DAYS, CELL_DEGREES, PERSISTENT_MIN_DAYS
from app.thermal.firms import MAX_DAY_RANGE, FirmsError, build_area_url, fetch_csv, parse_csv
from app.thermal.history import ARCHIVE_FOR, availability_url, fetch_csv_any, parse_availability
from app.thermal.tracks import haversine_km

logger = logging.getLogger("mcho.ucdp.heat")

FAMILIES = ("VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT")  # two satellites, about four passes a day between them
RADIUS_KM = {1: 5.0, 2: 25.0}
WINDOW_PAD_DAYS = 1
MAX_REQUESTS_PER_RUN = 40
GROUP_DEGREES = 1.0
GROUP_DAYS = 7


def event_window(event: dict[str, Any]) -> tuple[date, date]:
    return event["date_start"] - timedelta(days=WINDOW_PAD_DAYS), event["date_end"] + timedelta(days=WINDOW_PAD_DAYS)


def group_events(events: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Events close in space (1° cells) and time (7-day bins) share FIRMS requests."""
    groups: dict[tuple[int, int, int], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        key = (math.floor(event["latitude"] / GROUP_DEGREES), math.floor(event["longitude"] / GROUP_DEGREES),
               event["date_start"].toordinal() // GROUP_DAYS)
        groups[key].append(event)
    return list(groups.values())


def group_area(group: list[dict[str, Any]]) -> str:
    """Bounding box covering every event's radius, as FIRMS 'west,south,east,north'."""
    west = south = math.inf
    east = north = -math.inf
    for event in group:
        radius = RADIUS_KM[event["where_prec"]]
        dlat = radius / 111.0
        dlon = radius / (111.0 * max(math.cos(math.radians(event["latitude"])), 0.2))
        west, east = min(west, event["longitude"] - dlon), max(east, event["longitude"] + dlon)
        south, north = min(south, event["latitude"] - dlat), max(north, event["latitude"] + dlat)
    clamp = lambda value, limit: max(-limit, min(limit, value))  # noqa: E731
    return f"{clamp(west, 180):.3f},{clamp(south, 90):.3f},{clamp(east, 180):.3f},{clamp(north, 90):.3f}"


def group_days(group: list[dict[str, Any]]) -> tuple[date, date]:
    """First and last day needed: the 7 baseline days before the earliest window, to the latest window end."""
    first = min(event_window(e)[0] for e in group) - timedelta(days=BASELINE_DAYS)
    last = max(event_window(e)[1] for e in group)
    return first, last


def plan_chunks(first: date, last: date, family: str, ranges: dict[str, tuple[date, date]]) -> list[tuple[str, date, int]] | None:
    """(product, start, days) chunks of at most 5 days; None if any day is not available in FIRMS yet."""
    archive = ARCHIVE_FOR.get(family)
    chunks: list[tuple[str, date, int]] = []
    day = first
    while day <= last:
        def covers(product: str | None, d: date) -> bool:
            span = ranges.get(product) if product else None
            return bool(span and span[0] <= d <= span[1])
        product = archive if covers(archive, day) else family if covers(family, day) else None
        if product is None:
            return None
        length = 1
        while length < MAX_DAY_RANGE and day + timedelta(days=length) <= last and covers(product, day + timedelta(days=length)):
            length += 1
        chunks.append((product, day, length))
        day += timedelta(days=length)
    return chunks


def assess(event: dict[str, Any], detections: list[dict[str, Any]]) -> dict[str, Any]:
    """Heat near one event, separating persistent sites; detections need latitude, longitude, day, frp."""
    start, end = event_window(event)
    baseline_start = start - timedelta(days=BASELINE_DAYS)
    radius = RADIUS_KM[event["where_prec"]]
    baseline_days: dict[tuple[int, int], set[date]] = defaultdict(set)
    for d in detections:
        if baseline_start <= d["day"] < start:
            baseline_days[(math.floor(d["longitude"] / CELL_DEGREES), math.floor(d["latitude"] / CELL_DEGREES))].add(d["day"])
    persistent = {cell for cell, days in baseline_days.items() if len(days) >= PERSISTENT_MIN_DAYS}
    matched, excluded = [], 0
    for d in detections:
        if not start <= d["day"] <= end:
            continue
        distance = haversine_km(event["longitude"], event["latitude"], d["longitude"], d["latitude"])
        if distance > radius:
            continue
        if (math.floor(d["longitude"] / CELL_DEGREES), math.floor(d["latitude"] / CELL_DEGREES)) in persistent:
            excluded += 1
        else:
            matched.append((distance, d))
    status = "heat" if matched else "persistent_only" if excluded else "no_heat"
    frps = [d["frp"] for _, d in matched if d["frp"] is not None]
    return {
        "heat_status": status, "heat_detections": len(matched), "heat_persistent_excluded": excluded,
        "heat_max_frp": max(frps) if frps else None, "heat_radius_km": radius,
        "heat_nearest_km": round(min(distance for distance, _ in matched), 2) if matched else None,
    }


def check_pending_events(db: Session, client: httpx.Client, now: datetime, max_requests: int = MAX_REQUESTS_PER_RUN) -> int:
    """Run heat cross-checks for pending events within a request budget. Returns events checked."""
    key = settings.nasa_firms_api_key.strip()
    if not key:
        return 0
    rows = db.execute(text("""
        SELECT id, latitude, longitude, date_start, date_end, where_prec FROM ucdp_events
        WHERE heat_status = 'pending' ORDER BY date_start DESC LIMIT 2000
    """)).mappings().all()
    db.commit()  # no transaction held during FIRMS requests
    if not rows:
        return 0
    try:
        ranges = parse_availability(fetch_csv_any(client, availability_url(key)))
    except FirmsError as exc:
        logger.warning("ucdp_heat_availability_failed summary=%s", exc)
        return 0
    checked = requests = 0
    for group in group_events([dict(r) for r in rows]):
        first, last = group_days(group)
        plans = {family: plan_chunks(first, last, family, ranges) for family in FAMILIES}
        if any(plan is None for plan in plans.values()):
            continue  # some days are not in FIRMS yet; try again later
        cost = sum(len(plan) for plan in plans.values() if plan)
        if requests + cost > max_requests:
            break
        area = group_area(group)
        detections: list[dict[str, Any]] = []
        try:
            for plan in plans.values():
                for product, start, length in plan or []:
                    parsed, _ = parse_csv(fetch_csv(client, build_area_url(key, product, area, length, start)), product)
                    requests += 1
                    detections += [{"latitude": p["latitude"], "longitude": p["longitude"], "frp": p.get("frp"),
                                    "day": date.fromisoformat(p["acquired_at"][:10])} for p in parsed]
        except FirmsError as exc:
            logger.warning("ucdp_heat_fetch_failed summary=%s", exc)
            break
        products = ",".join(sorted({product for plan in plans.values() for product, _, _ in plan or []}))[:120]
        for event in group:
            result = assess(event, detections)
            db.execute(text("""
                UPDATE ucdp_events SET heat_status = :heat_status, heat_detections = :heat_detections,
                    heat_persistent_excluded = :heat_persistent_excluded, heat_max_frp = :heat_max_frp,
                    heat_nearest_km = :heat_nearest_km, heat_radius_km = :heat_radius_km, heat_products = :products,
                    heat_checked_at = :checked_at
                WHERE id = :id AND heat_status = 'pending'
            """), {**result, "products": products, "checked_at": now, "id": event["id"]})
            checked += 1
        db.commit()
    logger.info("ucdp_heat_checked events=%s requests=%s", checked, requests)
    return checked
