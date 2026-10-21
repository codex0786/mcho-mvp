"""Summaries of IMF PortWatch aggregates for chokepoints and MENA ports.

All figures are computed by MCHO from PortWatch's published daily values:
7-day averages (at least 5 of the 7 days present), the same 7 calendar days one
year earlier, and 90-day daily series. Days without a published value stay
empty; they are never treated as zero.
"""
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.maritime.portwatch import ATTRIBUTION, SOURCE_VERSION
from app.thermal.history import last_year

SERIES_DAYS = 90
WINDOW_DAYS = 7
MIN_DAYS = 5
MAX_PORTS = 25

CAVEATS = (
    "Counts come from AIS ship signals processed by the IMF. Ships that switch off AIS, or are missed by receivers, are not "
    "counted, so counts can understate traffic, especially near conflict zones. PortWatch publishes with a delay of a few "
    "days. Figures show traffic levels only, never individual vessels."
)


def _avg(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(mean(present), 1) if len(present) >= MIN_DAYS else None


def _change(current: float | None, previous: float | None) -> float | None:
    return round((current - previous) / previous * 100) if current is not None and previous else None


def maritime_overview(db: Session, now: datetime, country: str | None = None) -> dict[str, Any]:
    latest = db.scalar(text("SELECT max(period_start) FROM maritime_aggregates WHERE source_version = :v AND metric = 'transits_total'"),
                       {"v": SOURCE_VERSION})
    areas = db.execute(text("""
        SELECT id, kind, name, country_code, ST_X(geometry) AS longitude, ST_Y(geometry) AS latitude, reference_vessels_per_year
        FROM maritime_areas
        WHERE kind = 'chokepoint' OR (CAST(:country AS text) IS NULL OR country_code = :country)
        ORDER BY kind, reference_vessels_per_year DESC NULLS LAST, name
    """), {"country": country}).mappings().all()
    base = {"latest_day": None, "chokepoints": [], "ports": [], "attribution": ATTRIBUTION, "caveats": CAVEATS,
            "transformation": "7-day averages, year-on-year changes and 90-day series are computed by MCHO from PortWatch daily values.",
            "country": country, "generated_at": now.isoformat()}
    if latest is None or not areas:
        return base
    end = latest.astimezone(timezone.utc).date()
    days = [end - timedelta(days=offset) for offset in range(SERIES_DAYS - 1, -1, -1)]
    window = days[-WINDOW_DAYS:]
    prior = [last_year(day) for day in window]
    rows = db.execute(text("""
        SELECT area_id, (period_start AT TIME ZONE 'UTC')::date AS day, metric, value
        FROM maritime_aggregates
        WHERE source_version = :v AND area_id = ANY(:areas)
          AND ((period_start >= :start AND period_start < :finish) OR (period_start >= :prior_start AND period_start < :prior_finish))
    """), {
        "v": SOURCE_VERSION, "areas": [a["id"] for a in areas],
        "start": datetime.combine(days[0], datetime.min.time(), tzinfo=timezone.utc),
        "finish": datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc),
        "prior_start": datetime.combine(prior[0], datetime.min.time(), tzinfo=timezone.utc),
        "prior_finish": datetime.combine(prior[-1] + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc),
    }).all()
    values: dict[tuple[str, str, date], float] = {(r.area_id, r.metric, r.day): r.value for r in rows}

    def series(area: str, metric: str, span: list[date]) -> list[float | None]:
        return [values.get((area, metric, day)) for day in span]

    for area in areas:
        primary = "transits_total" if area["kind"] == "chokepoint" else "portcalls_total"
        current = _avg(series(area["id"], primary, window))
        previous = _avg(series(area["id"], primary, prior))
        item: dict[str, Any] = {
            "id": area["id"], "name": area["name"], "country_code": area["country_code"],
            "longitude": round(area["longitude"], 4), "latitude": round(area["latitude"], 4),
            "metric": primary, "avg_7d": current, "avg_7d_last_year": previous, "change_vs_last_year_pct": _change(current, previous),
            "series": [{"day": day.isoformat(), "value": v} for day, v in zip(days, series(area["id"], primary, days))],
        }
        if area["kind"] == "chokepoint":
            item["tankers_avg_7d"] = _avg(series(area["id"], "transits_tanker", window))
            item["capacity_dwt_avg_7d"] = _avg(series(area["id"], "capacity_dwt", window))
            base["chokepoints"].append(item)
        else:
            imports = [v for v in series(area["id"], "import_tonnes", window) if v is not None]
            exports = [v for v in series(area["id"], "export_tonnes", window) if v is not None]
            item["import_tonnes_7d"] = round(sum(imports)) if len(imports) >= MIN_DAYS else None
            item["export_tonnes_7d"] = round(sum(exports)) if len(exports) >= MIN_DAYS else None
            base["ports"].append(item)
    base["ports"] = base["ports"][:MAX_PORTS]
    base["latest_day"] = end.isoformat()
    return base
