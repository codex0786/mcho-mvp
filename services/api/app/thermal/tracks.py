"""Follow heat activity across days: daily clusters linked into tracks.

Method (documented in docs/satellite-thermal.md):
1. Persistent sites (gas flares, industry) are removed: cells active on at least 4 of
   the 7 baseline days before the period, or on at least 60% of the period's days.
2. For each UTC day, remaining detections are clustered with DBSCAN
   (~5 km neighbourhood, at least 3 detections).
3. Each day's clusters are linked to the nearest track whose latest cluster is
   within 30 km and at most 2 days earlier (one cloudy day may be skipped).
4. Tracks spanning at least 2 distinct days are reported, with their path,
   displacement, direction and speed.
A track describes how heat moved; it says nothing about what caused it.
"""
import math
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.thermal.analysis import BASELINE_DAYS, CELL_DEGREES, PERSISTENT_MIN_DAYS

CLUSTER_EPS_DEGREES = 0.05  # ~5 km
CLUSTER_MIN_POINTS = 3
LINK_KM = 30.0
MAX_GAP_DAYS = 2
MAX_TRACKS = 40
_cache: dict[tuple, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()
CACHE_SECONDS = 600

_DAY_CLUSTERS = """
WITH baseline AS (
    SELECT floor(longitude / :cell)::int AS cx, floor(latitude / :cell)::int AS cy,
           count(DISTINCT (acquired_at AT TIME ZONE 'UTC')::date) AS days
    FROM thermal_detections
    WHERE acquired_at >= :baseline_start AND acquired_at < :start {country_filter}
    GROUP BY 1, 2
), period AS (
    SELECT floor(longitude / :cell)::int AS cx, floor(latitude / :cell)::int AS cy,
           count(DISTINCT (acquired_at AT TIME ZONE 'UTC')::date) AS days
    FROM thermal_detections
    WHERE acquired_at >= :start AND acquired_at <= :now {country_filter}
    GROUP BY 1, 2
), points AS (
    SELECT d.geometry, d.longitude, d.latitude, d.frp, d.country_code,
           (d.acquired_at AT TIME ZONE 'UTC')::date AS day
    FROM thermal_detections AS d
    LEFT JOIN baseline AS b ON b.cx = floor(d.longitude / :cell)::int AND b.cy = floor(d.latitude / :cell)::int
    LEFT JOIN period AS p ON p.cx = floor(d.longitude / :cell)::int AND p.cy = floor(d.latitude / :cell)::int
    WHERE d.acquired_at >= :start AND d.acquired_at <= :now {country_filter_d}
      AND coalesce(b.days, 0) < :persistent_days AND coalesce(p.days, 0) < :period_persistent_days
), clustered AS (
    SELECT points.*, ST_ClusterDBSCAN(geometry, eps := :eps, minpoints := :minpoints) OVER (PARTITION BY day) AS cid
    FROM points
)
SELECT day, cid, count(*) AS detections, avg(longitude) AS longitude, avg(latitude) AS latitude,
       max(frp) AS max_frp, mode() WITHIN GROUP (ORDER BY country_code) AS country_code
FROM clustered
WHERE cid IS NOT NULL
GROUP BY day, cid
ORDER BY day, detections DESC
"""


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bearing_degrees(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass(bearing: float) -> str:
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((bearing + 22.5) // 45) % 8]


def link_clusters(clusters: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Greedy day-by-day linking. ``clusters`` need day, longitude, latitude, detections."""
    tracks: list[list[dict[str, Any]]] = []
    for day in sorted({c["day"] for c in clusters}):
        todays = sorted((c for c in clusters if c["day"] == day), key=lambda c: -c["detections"])
        open_tracks = [t for t in tracks if 0 < (day - t[-1]["day"]).days <= MAX_GAP_DAYS]
        pairs = sorted(
            ((haversine_km(t[-1]["longitude"], t[-1]["latitude"], c["longitude"], c["latitude"]), ti, ci)
             for ti, t in enumerate(open_tracks) for ci, c in enumerate(todays)),
            key=lambda pair: pair[0],
        )
        used_tracks: set[int] = set()
        used_clusters: set[int] = set()
        for distance, ti, ci in pairs:
            if distance > LINK_KM:
                break
            if ti in used_tracks or ci in used_clusters:
                continue
            open_tracks[ti].append(todays[ci])
            used_tracks.add(ti)
            used_clusters.add(ci)
        tracks.extend([c] for ci, c in enumerate(todays) if ci not in used_clusters)
    return tracks


def _summarise(track: list[dict[str, Any]], today: date, names: dict[str, str]) -> dict[str, Any]:
    first, last = track[0], track[-1]
    displacement = haversine_km(first["longitude"], first["latitude"], last["longitude"], last["latitude"])
    span_days = max((last["day"] - first["day"]).days, 1)
    bearing = bearing_degrees(first["longitude"], first["latitude"], last["longitude"], last["latitude"])
    countries = [c["country_code"] for c in track]
    country = max(set(countries), key=countries.count)
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[round(c["longitude"], 4), round(c["latitude"], 4)] for c in track]},
        "properties": {
            "country_code": country, "country": names.get(country, country),
            "first_day": first["day"].isoformat(), "last_day": last["day"].isoformat(),
            "days_active": len({c["day"] for c in track}),
            "detections": sum(c["detections"] for c in track),
            "max_frp_mw": max((c["max_frp"] or 0) for c in track) or None,
            "displacement_km": round(displacement, 1),
            "direction": compass(bearing) if displacement >= 2 else None,
            "bearing_degrees": round(bearing) if displacement >= 2 else None,
            "km_per_day": round(displacement / span_days, 1),
            "active": (today - last["day"]).days <= 1,
            "latest": {"longitude": round(last["longitude"], 4), "latitude": round(last["latitude"], 4)},
            "daily": [{"day": c["day"].isoformat(), "detections": c["detections"],
                       "longitude": round(c["longitude"], 4), "latitude": round(c["latitude"], 4)} for c in track],
        },
    }


def thermal_tracks(db: Session, now: datetime, days: int, country: str | None = None) -> dict[str, Any]:
    start = datetime.combine(now.astimezone(timezone.utc).date() - timedelta(days=days - 1), datetime.min.time(), tzinfo=timezone.utc)
    refreshed = db.scalar(text("SELECT max(finished_at) FROM thermal_refreshes WHERE status = 'succeeded'"))
    key = (days, country, refreshed, now.astimezone(timezone.utc).date())
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] > now.timestamp() - CACHE_SECONDS:
            return cached[1]
    country_filter = " AND country_code = :country" if country else ""
    sql = _DAY_CLUSTERS.format(country_filter=country_filter, country_filter_d=country_filter.replace("country_code", "d.country_code"))
    rows = db.execute(text(sql), {
        "cell": CELL_DEGREES, "start": start, "now": now, "baseline_start": start - timedelta(days=BASELINE_DAYS),
        "persistent_days": PERSISTENT_MIN_DAYS, "period_persistent_days": max(PERSISTENT_MIN_DAYS, math.ceil(0.6 * days)),
        "eps": CLUSTER_EPS_DEGREES, "minpoints": CLUSTER_MIN_POINTS, "country": country,
    }).mappings().all()
    clusters = [dict(row) for row in rows]
    names = dict(db.execute(text("SELECT iso_a3, name FROM country_boundaries")).all())
    today = now.astimezone(timezone.utc).date()
    tracks = [t for t in link_clusters(clusters) if len({c["day"] for c in t}) >= 2]
    tracks.sort(key=lambda t: sum(c["detections"] for c in t), reverse=True)
    result = {
        "type": "FeatureCollection",
        "features": [_summarise(t, today, names) for t in tracks[:MAX_TRACKS]],
        "total_tracks": len(tracks), "days": days, "country": country,
        "daily_clusters": len(clusters), "generated_at": now.isoformat(),
        "method": {
            "cluster_eps_km": round(CLUSTER_EPS_DEGREES * 111), "cluster_min_detections": CLUSTER_MIN_POINTS,
            "link_km": LINK_KM, "max_gap_days": MAX_GAP_DAYS,
            "persistent_rule": f"Excluded: ~2 km cells active on at least {PERSISTENT_MIN_DAYS} of the {BASELINE_DAYS} days before the period, or on at least 60% of the period's days.",
        },
        "caveats": ("A track links heat clusters on consecutive days that are close together. It shows how heat moved, "
                    "not why: separate fires near each other can be linked, and clouds can break a track. Not a verified event."),
    }
    with _cache_lock:
        if len(_cache) > 100:
            _cache.clear()
        _cache[key] = (now.timestamp(), result)
    return result
