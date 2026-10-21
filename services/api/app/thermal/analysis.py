"""Derive explainable insights from stored satellite heat detections.

Method (documented for users in docs/satellite-thermal.md):
- Window: detections acquired in the last ``hours`` (24 by default).
- Baseline: the 7 days before the window.
- Each detection falls in a ~2 km grid cell (0.02 degrees). A cell with detections
  on at least 4 distinct baseline days is *persistent* (typically gas flares or
  industry). A cell with no baseline detections is *new*. Otherwise *recurring*.
- Country activity compares non-persistent detections in the window with the
  baseline's non-persistent daily average.
- New-activity clusters group new detections into ~10 km cells (0.1 degrees).
None of these labels says what caused the heat; they are leads for review.
"""
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

CELL_DEGREES = 0.02
CLUSTER_DEGREES = 0.1
BASELINE_DAYS = 7
PERSISTENT_MIN_DAYS = 4
ELEVATED_MIN_COUNT = 10
ELEVATED_RATIO = 2.0
MAX_FEATURES = 5_000

CAVEATS = (
    "Satellite heat detections (NASA FIRMS, VIIRS ~375 m). Each is a heat signature, not a "
    "verified event: causes include fires from conflict, crop burning, wildfires, gas flares "
    "and industry. Clouds, smoke and satellite timing leave gaps; no detection does not mean "
    "nothing happened. Not for targeting or tactical use."
)

_CLASSIFIED = """
WITH baseline AS (
    SELECT floor(longitude / :cell)::int AS cx, floor(latitude / :cell)::int AS cy,
           count(DISTINCT (acquired_at AT TIME ZONE 'UTC')::date) AS days,
           count(*) AS detections
    FROM thermal_detections
    WHERE acquired_at >= :baseline_start AND acquired_at < :window_start {baseline_filter}
    GROUP BY 1, 2
), recent AS (
    SELECT d.*, floor(d.longitude / :cell)::int AS cx, floor(d.latitude / :cell)::int AS cy
    FROM thermal_detections AS d
    WHERE d.acquired_at >= :window_start AND d.acquired_at <= :now {recent_filter}
), classified AS (
    SELECT r.*, coalesce(b.days, 0) AS baseline_days,
           CASE WHEN coalesce(b.days, 0) >= :persistent_days THEN 'persistent'
                WHEN coalesce(b.days, 0) = 0 THEN 'new'
                ELSE 'recurring' END AS classification
    FROM recent AS r LEFT JOIN baseline AS b ON b.cx = r.cx AND b.cy = r.cy
)
"""


def _window(now: datetime, hours: int) -> dict[str, Any]:
    window_start = now - timedelta(hours=hours)
    return {
        "now": now, "window_start": window_start,
        "baseline_start": window_start - timedelta(days=BASELINE_DAYS),
        "cell": CELL_DEGREES, "persistent_days": PERSISTENT_MIN_DAYS,
    }


def detections_geojson(db: Session, now: datetime, hours: int, bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    west, south, east, north = bbox
    params = {**_window(now, hours), "west": west, "south": south, "east": east, "north": north,
              "limit": MAX_FEATURES + 1, "pad": CELL_DEGREES}
    spatial = "AND geometry && ST_MakeEnvelope(:west - :pad, :south - :pad, :east + :pad, :north + :pad, 4326)"
    sql = _CLASSIFIED.format(baseline_filter=spatial, recent_filter=spatial.replace("geometry", "d.geometry")) + """
    SELECT c.id, c.latitude, c.longitude, c.acquired_at, c.frp, c.confidence, c.satellite, c.product,
           c.daynight, c.country_code, cb.name AS country_name, c.classification, c.baseline_days
    FROM classified AS c JOIN country_boundaries AS cb ON cb.iso_a3 = c.country_code
    WHERE c.longitude BETWEEN :west AND :east AND c.latitude BETWEEN :south AND :north
    -- When the limit is hit, keep activity: new, then recurring, then persistent sites.
    ORDER BY CASE c.classification WHEN 'new' THEN 0 WHEN 'recurring' THEN 1 ELSE 2 END, c.acquired_at DESC
    LIMIT :limit
    """
    rows = db.execute(text(sql), params).mappings().all()
    truncated = len(rows) > MAX_FEATURES
    features = [{
        "type": "Feature", "id": str(row["id"]),
        "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]},
        "properties": {
            "acquired_at": row["acquired_at"].isoformat(), "frp_mw": row["frp"],
            "confidence": row["confidence"], "satellite": row["satellite"], "product": row["product"],
            "daynight": row["daynight"], "country_code": row["country_code"], "country": row["country_name"],
            "classification": row["classification"], "baseline_days": row["baseline_days"],
        },
    } for row in rows[:MAX_FEATURES]]
    return {"type": "FeatureCollection", "features": features, "truncated": truncated, "feature_limit": MAX_FEATURES}


def insights(db: Session, now: datetime, hours: int = 24) -> dict[str, Any]:
    params = {**_window(now, hours), "cluster": CLUSTER_DEGREES}
    classified = _CLASSIFIED.format(baseline_filter="", recent_filter="")
    countries = db.execute(text(classified + """
    , window_counts AS (
        SELECT country_code,
               count(*) FILTER (WHERE classification <> 'persistent') AS active,
               count(*) FILTER (WHERE classification = 'new') AS new,
               count(*) FILTER (WHERE classification = 'persistent') AS persistent,
               max(frp) AS max_frp
        FROM classified GROUP BY country_code
    ), baseline_counts AS (
        SELECT d.country_code, count(*)::float / :baseline_days AS daily_average
        FROM thermal_detections AS d
        LEFT JOIN baseline AS b ON b.cx = floor(d.longitude / :cell)::int AND b.cy = floor(d.latitude / :cell)::int
        WHERE d.acquired_at >= :baseline_start AND d.acquired_at < :window_start
          AND coalesce(b.days, 0) < :persistent_days
        GROUP BY d.country_code
    )
    SELECT cb.iso_a3, cb.iso_a2, cb.name, coalesce(w.active, 0) AS active, coalesce(w.new, 0) AS new,
           coalesce(w.persistent, 0) AS persistent, w.max_frp, coalesce(b.daily_average, 0) AS baseline_daily_average
    FROM country_boundaries AS cb
    LEFT JOIN window_counts AS w ON w.country_code = cb.iso_a3
    LEFT JOIN baseline_counts AS b ON b.country_code = cb.iso_a3
    ORDER BY coalesce(w.active, 0) DESC, cb.name
    """), {**params, "baseline_days": BASELINE_DAYS}).mappings().all()

    clusters = db.execute(text(classified + """
    SELECT c.country_code, cb.name AS country_name,
           floor(c.longitude / :cluster)::int AS gx, floor(c.latitude / :cluster)::int AS gy,
           count(*) AS detections, avg(c.longitude) AS longitude, avg(c.latitude) AS latitude,
           max(c.frp) AS max_frp, min(c.acquired_at) AS first_seen, max(c.acquired_at) AS last_seen,
           count(DISTINCT c.satellite) AS satellites
    FROM classified AS c JOIN country_boundaries AS cb ON cb.iso_a3 = c.country_code
    WHERE c.classification = 'new'
    GROUP BY c.country_code, cb.name, gx, gy
    HAVING count(*) >= 2
    ORDER BY count(*) DESC, max(c.frp) DESC NULLS LAST
    LIMIT 10
    """), params).mappings().all()

    coverage_start = db.scalar(text("SELECT min(acquired_at) FROM thermal_detections"))
    latest_detection = db.scalar(text("SELECT max(acquired_at) FROM thermal_detections"))
    baseline_days_available = 0.0
    if coverage_start and coverage_start < params["window_start"]:
        baseline_days_available = round(min(BASELINE_DAYS, (params["window_start"] - coverage_start).total_seconds() / 86400), 1)

    country_items = []
    for row in countries:
        average = float(row["baseline_daily_average"])
        daily_rate = row["active"] * 24 / hours
        elevated = row["active"] >= ELEVATED_MIN_COUNT and (average == 0 or daily_rate >= ELEVATED_RATIO * average)
        country_items.append({
            "iso_a3": row["iso_a3"], "iso_a2": row["iso_a2"], "name": row["name"],
            "active_detections": row["active"], "new_detections": row["new"], "persistent_detections": row["persistent"],
            "baseline_daily_average": round(average, 1),
            "ratio_to_baseline": round(daily_rate / average, 1) if average else None,
            "max_frp_mw": row["max_frp"], "elevated": elevated,
        })
    return {
        "window_hours": hours, "window_start": params["window_start"].isoformat(), "generated_at": now.isoformat(),
        "latest_detection_at": latest_detection.isoformat() if latest_detection else None,
        "baseline_days_available": baseline_days_available,
        "totals": {
            "active_detections": sum(item["active_detections"] for item in country_items),
            "new_detections": sum(item["new_detections"] for item in country_items),
            "persistent_detections": sum(item["persistent_detections"] for item in country_items),
            "elevated_countries": sum(1 for item in country_items if item["elevated"]),
        },
        "countries": country_items,
        "new_activity_clusters": [{
            "country_code": row["country_code"], "country": row["country_name"], "detections": row["detections"],
            "longitude": round(float(row["longitude"]), 4), "latitude": round(float(row["latitude"]), 4),
            "max_frp_mw": row["max_frp"], "first_seen": row["first_seen"].isoformat(),
            "last_seen": row["last_seen"].isoformat(), "satellites": row["satellites"],
        } for row in clusters],
        "method": {
            "cell_degrees": CELL_DEGREES, "cluster_degrees": CLUSTER_DEGREES, "baseline_days": BASELINE_DAYS,
            "persistent_min_days": PERSISTENT_MIN_DAYS, "elevated_rule":
                f"at least {ELEVATED_MIN_COUNT} non-persistent detections and at least {ELEVATED_RATIO:g}x the baseline daily average",
        },
        "caveats": CAVEATS,
        "source": {"name": "NASA FIRMS", "url": "https://firms.modaps.eosdis.nasa.gov/", "attribution":
                   "NASA Fire Information for Resource Management System (FIRMS), VIIRS 375 m NRT"},
    }
