"""Summaries of UCDP Candidate events and their satellite heat cross-checks.

Figures are UCDP's own: events and best/low/high death estimates summed by
MCHO over the latest months whose releases were downloaded. Months that were
not downloaded are listed as missing, never counted as zero.
"""
import json
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.conflict.heat_match import RADIUS_KM
from app.conflict.ucdp import ATTRIBUTION, CITATION, VIOLENCE_TYPES
from app.core.config import settings
from app.thermal.tracks import thermal_tracks

PERIOD_MONTHS = 3
CONTEXT_DAYS = 180
CONTEXT_KM = 25.0
LIST_SIZE = 12
MAX_MAP_EVENTS = 3000

CAVEATS = (
    "UCDP Candidate data are preliminary: events are coded from news and NGO reports each month, can be revised, and "
    "only count organised violence with at least one direct death. Death figures are UCDP's best estimates with a low-high "
    "range. Coverage depends on reporting, which is thin in some areas. Each monthly release appears about three weeks after "
    "the month ends."
)
HEAT_NOTE = (
    "Heat cross-check: for events with a precise place (exact, or within ~25 km) and date (within 6 days), MCHO looked for "
    "NASA FIRMS VIIRS heat detections within 5 km (exact place) or 25 km, from the day before to the day after the event, "
    "leaving out persistent sites such as gas flares. A match means heat was seen near a verified event at about the same "
    "time; it does not prove the event caused it. No heat does not mean nothing burned: clouds, smoke and satellite timing "
    "leave gaps."
)
TRANSFORMATION = "Totals by country and month, the heat cross-check and the proximity to current heat fronts are computed by MCHO from UCDP's event records."


def _month(release: str) -> date | None:
    try:
        yy, _, month = release.split(".")
        return date(2000 + int(yy), int(month), 1)
    except ValueError:
        return None


def _month_end(first: date) -> date:
    return (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def _event(row: Any, names: dict[str, str]) -> dict[str, Any]:
    return {
        "id": row["id"], "date_start": row["date_start"].isoformat(), "date_end": row["date_end"].isoformat(),
        "country_code": row["country_code"], "country": names.get(row["country_code"], row["country_code"]),
        "place": row["where_description"] or row["adm_1"] or "Place not given", "adm_1": row["adm_1"],
        "type": VIOLENCE_TYPES.get(row["type_of_violence"], "Unknown"), "type_code": row["type_of_violence"],
        "dyad": row["dyad_name"], "conflict": row["conflict_name"], "side_a": row["side_a"], "side_b": row["side_b"],
        "deaths_best": row["deaths_best"], "deaths_low": row["deaths_low"], "deaths_high": row["deaths_high"],
        "deaths_civilians": row["deaths_civilians"], "code_status": row["code_status"],
        "where_prec": row["where_prec"], "date_prec": row["date_prec"],
        "longitude": round(row["longitude"], 4), "latitude": round(row["latitude"], 4),
        "heat": {"status": row["heat_status"], "detections": row["heat_detections"], "nearest_km": row["heat_nearest_km"],
                 "radius_km": row["heat_radius_km"], "max_frp_mw": row["heat_max_frp"],
                 "persistent_excluded": row["heat_persistent_excluded"]},
    }


def fronts_near_violence(db: Session, now: datetime, country: str | None) -> list[dict[str, Any]]:
    """Active moving heat fronts (last 7 days) within 25 km of UCDP events in the previous 180 days."""
    tracks = [f for f in thermal_tracks(db, now, 7, country)["features"] if f["properties"]["active"]]
    if not tracks:
        return []
    points = [{"i": i, "lon": t["properties"]["latest"]["longitude"], "lat": t["properties"]["latest"]["latitude"]} for i, t in enumerate(tracks)]
    rows = db.execute(text("""
        SELECT p.i, count(e.id) AS events, coalesce(sum(e.deaths_best), 0) AS deaths, max(e.date_end) AS latest,
               mode() WITHIN GROUP (ORDER BY e.dyad_name) AS dyad,
               min(ST_DistanceSphere(e.geometry, ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326))) / 1000 AS nearest_km
        FROM json_to_recordset(CAST(:points AS json)) AS p(i int, lon double precision, lat double precision)
        JOIN ucdp_events AS e ON ST_DWithin(e.geometry::geography, ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326)::geography, :metres)
             AND e.date_end >= :since
        GROUP BY p.i
    """), {"points": json.dumps(points), "metres": CONTEXT_KM * 1000, "since": now.date() - timedelta(days=CONTEXT_DAYS)}).mappings().all()
    out = []
    for row in rows:
        p = tracks[row["i"]]["properties"]
        out.append({
            "country": p["country"], "country_code": p["country_code"], "first_day": p["first_day"], "last_day": p["last_day"],
            "detections": p["detections"], "latest": p["latest"], "ucdp_events": row["events"], "ucdp_deaths_best": int(row["deaths"]),
            "ucdp_latest": row["latest"].isoformat(), "ucdp_dyad": row["dyad"], "nearest_event_km": round(row["nearest_km"], 1),
        })
    return sorted(out, key=lambda f: (-f["ucdp_events"], -f["detections"]))[:LIST_SIZE]


def conflict_overview(db: Session, now: datetime, country: str | None = None) -> dict[str, Any]:
    names = dict(db.execute(text("SELECT iso_a3, name FROM country_boundaries")).all())
    releases = db.execute(text("SELECT release, fetched_at, rows_mena FROM ucdp_releases")).mappings().all()
    fetched = sorted(((_month(r["release"]), r) for r in releases if _month(r["release"])), key=lambda pair: pair[0], reverse=True)
    base: dict[str, Any] = {
        "country": country, "generated_at": now.isoformat(), "attribution": ATTRIBUTION, "citation": CITATION,
        "caveats": CAVEATS, "heat_note": HEAT_NOTE, "transformation": TRANSFORMATION,
        "releases": [{"release": r["release"], "month": m.strftime("%Y-%m"), "fetched_at": r["fetched_at"].isoformat(),
                      "events_mena": r["rows_mena"]} for m, r in fetched],
        "period": None, "totals": None, "by_country": [], "by_month": [], "top_events": [], "events_with_heat": [],
        "fronts_near_violence": [], "events": {"type": "FeatureCollection", "features": []},
        "heat_check": {"configured": bool(settings.nasa_firms_api_key.strip())},
    }
    if not fetched:
        return base
    latest = fetched[0][0]
    months = []
    first = latest
    for _ in range(PERIOD_MONTHS):
        months.append(first)
        first = (first - timedelta(days=1)).replace(day=1)
    months.reverse()
    have = {m for m, _ in fetched}
    start, end = months[0], _month_end(latest)
    base["period"] = {"start": start.isoformat(), "end": end.isoformat(), "months": [m.strftime("%Y-%m") for m in months],
                      "missing_months": [m.strftime("%Y-%m") for m in months if m not in have]}
    params = {"start": start, "end": end, "country": country}
    where = "date_start >= :start AND date_start <= :end AND (CAST(:country AS text) IS NULL OR country_code = :country)"

    totals = db.execute(text(f"""
        SELECT count(*) AS events, coalesce(sum(deaths_best), 0) AS deaths_best, coalesce(sum(deaths_low), 0) AS deaths_low,
               coalesce(sum(deaths_high), 0) AS deaths_high, coalesce(sum(deaths_civilians), 0) AS deaths_civilians
        FROM ucdp_events WHERE {where}
    """), params).mappings().one()
    base["totals"] = {k: int(v) for k, v in totals.items()}
    base["by_country"] = [
        {"country_code": r["country_code"], "country": names.get(r["country_code"], r["country_code"]), "events": r["events"],
         "deaths_best": int(r["deaths_best"]), "deaths_low": int(r["deaths_low"]), "deaths_high": int(r["deaths_high"]),
         "deaths_civilians": int(r["deaths_civilians"]),
         "by_type": {VIOLENCE_TYPES[t]: int(r[f"t{t}"]) for t in VIOLENCE_TYPES}}
        for r in db.execute(text(f"""
            SELECT country_code, count(*) AS events, sum(deaths_best) AS deaths_best, sum(deaths_low) AS deaths_low,
                   sum(deaths_high) AS deaths_high, sum(deaths_civilians) AS deaths_civilians,
                   coalesce(sum(deaths_best) FILTER (WHERE type_of_violence = 1), 0) AS t1,
                   coalesce(sum(deaths_best) FILTER (WHERE type_of_violence = 2), 0) AS t2,
                   coalesce(sum(deaths_best) FILTER (WHERE type_of_violence = 3), 0) AS t3
            FROM ucdp_events WHERE {where} GROUP BY country_code ORDER BY sum(deaths_best) DESC, count(*) DESC
        """), params).mappings().all()
    ]
    month_rows = {r["month"]: r for r in db.execute(text(f"""
        SELECT to_char(date_start, 'YYYY-MM') AS month, count(*) AS events, sum(deaths_best) AS deaths_best
        FROM ucdp_events WHERE {where} GROUP BY 1
    """), params).mappings().all()}
    base["by_month"] = [
        {"month": m.strftime("%Y-%m"), "fetched": m in have,
         "events": month_rows[m.strftime("%Y-%m")]["events"] if m.strftime("%Y-%m") in month_rows else (0 if m in have else None),
         "deaths_best": int(month_rows[m.strftime("%Y-%m")]["deaths_best"]) if m.strftime("%Y-%m") in month_rows else (0 if m in have else None)}
        for m in months
    ]
    status_counts = dict(db.execute(text(f"SELECT heat_status, count(*) FROM ucdp_events WHERE {where} GROUP BY 1"), params).all())
    checked = sum(status_counts.get(s, 0) for s in ("heat", "no_heat", "persistent_only"))
    base["heat_check"].update({
        "checked": checked, "with_heat": status_counts.get("heat", 0), "no_heat": status_counts.get("no_heat", 0),
        "persistent_only": status_counts.get("persistent_only", 0), "pending": status_counts.get("pending", 0),
        "not_checkable": status_counts.get("not_checkable", 0),
        "share_with_heat": round(status_counts.get("heat", 0) / checked, 2) if checked else None,
        "radius_km": RADIUS_KM,
    })
    columns = """id, date_start, date_end, country_code, where_description, adm_1, type_of_violence, dyad_name, conflict_name,
        side_a, side_b, deaths_best, deaths_low, deaths_high, deaths_civilians, code_status, where_prec, date_prec, longitude,
        latitude, heat_status, heat_detections, heat_nearest_km, heat_radius_km, heat_max_frp, heat_persistent_excluded"""
    base["top_events"] = [_event(r, names) for r in db.execute(text(
        f"SELECT {columns} FROM ucdp_events WHERE {where} ORDER BY deaths_best DESC, date_start DESC LIMIT {LIST_SIZE}"), params).mappings()]
    base["events_with_heat"] = [_event(r, names) for r in db.execute(text(
        f"SELECT {columns} FROM ucdp_events WHERE {where} AND heat_status = 'heat' "
        f"ORDER BY deaths_best DESC, heat_detections DESC LIMIT {LIST_SIZE}"), params).mappings()]
    features = db.execute(text(f"""
        SELECT id, longitude, latitude, date_start, type_of_violence, deaths_best, deaths_civilians, dyad_name,
               coalesce(where_description, adm_1, '') AS place, heat_status, country_code
        FROM ucdp_events WHERE {where} ORDER BY deaths_best DESC LIMIT {MAX_MAP_EVENTS}
    """), params).mappings().all()
    base["events"] = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": {"type": "Point", "coordinates": [round(f["longitude"], 4), round(f["latitude"], 4)]},
        "properties": {"id": f["id"], "date": f["date_start"].isoformat(), "type_code": f["type_of_violence"],
                       "type": VIOLENCE_TYPES.get(f["type_of_violence"]), "deaths_best": f["deaths_best"],
                       "deaths_civilians": f["deaths_civilians"], "dyad": f["dyad_name"], "place": f["place"],
                       "heat": f["heat_status"], "country": names.get(f["country_code"], f["country_code"])},
    } for f in features]}
    base["fronts_near_violence"] = fronts_near_violence(db, now, country)
    return base
