"""Public summary of UNOSAT damage assessments and their damage grid.

An assessment is drawn on the map unless a newer mapped assessment covers at
least 80% of its area: UNOSAT's comprehensive assessments are cumulative, so
drawing both would count the same structures twice.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.damage.unosat import ATTRIBUTION, CELL_DEGREES, CLASSES, HDX_DATASET

COVER_FRACTION = 0.8
SUMMARY_CHARS = 700
CAVEATS = (
    "UNOSAT assessments are preliminary and based on satellite imagery; most are not validated in the field. Only "
    "significant structural damage is visible from above. Each assessment covers a specific area on specific dates, "
    "so places without an assessment are unassessed, not undamaged."
)
TRANSFORMATION = (
    "MCHO counts UNOSAT's damaged structures by UNOSAT's own damage class in ~500 m grid cells (using the latest class "
    "recorded for each structure) and shares that grid under the same CC BY-SA licence. Structure locations are not shown."
)

_ASSESSMENTS = text("""
    WITH mapped AS (
        SELECT id, title, coalesce(imagery_date, published_on) AS day, extent
        FROM damage_assessments WHERE status = 'mapped' AND extent IS NOT NULL
    ), covered AS (
        SELECT a.id, (
            SELECT b.title FROM mapped AS b
            WHERE b.id <> a.id AND (b.day > a.day OR (b.day = a.day AND b.id > a.id))
              AND ST_Area(ST_Intersection(a.extent, b.extent)) >= :cover * ST_Area(a.extent)
            ORDER BY b.day DESC LIMIT 1
        ) AS superseded_by
        FROM mapped AS a
    )
    SELECT d.id, d.name, d.title, d.country_code, d.unosat_code, d.published_on, d.imagery_date, d.status, d.status_detail,
           d.licence, d.licence_url, d.summary, d.caveats, d.destroyed, d.severe, d.moderate, d.possible, d.unclassified,
           c.superseded_by, ST_XMin(d.extent) AS west, ST_YMin(d.extent) AS south, ST_XMax(d.extent) AS east, ST_YMax(d.extent) AS north
    FROM damage_assessments AS d LEFT JOIN covered AS c ON c.id = d.id
    WHERE CAST(:country AS text) IS NULL OR d.country_code = :country
    ORDER BY coalesce(d.imagery_date, d.published_on) DESC NULLS LAST, d.title
""")


def damage_overview(db: Session, now: datetime, country: str | None = None) -> dict[str, Any]:
    rows = db.execute(_ASSESSMENTS, {"cover": COVER_FRACTION, "country": country}).mappings().all()
    assessments, on_map = [], []
    for row in rows:
        shown = row["status"] == "mapped" and row["superseded_by"] is None
        if shown:
            on_map.append(row["id"])
        summary = row["summary"].replace("**", "").strip()
        assessments.append({
            "id": row["id"], "title": row["title"], "country_code": row["country_code"], "unosat_code": row["unosat_code"],
            "published_on": row["published_on"].isoformat() if row["published_on"] else None,
            "imagery_date": row["imagery_date"].isoformat() if row["imagery_date"] else None,
            "status": row["status"], "status_detail": row["status_detail"], "on_map": shown, "superseded_by": row["superseded_by"],
            "counts": {name: row[name] for name in CLASSES} if row["status"] == "mapped" else None,
            "bbox": [round(row[k], 4) for k in ("west", "south", "east", "north")] if row["west"] is not None else None,
            "hdx_url": HDX_DATASET + row["name"], "licence": row["licence"], "licence_url": row["licence_url"],
            "summary": summary if len(summary) <= SUMMARY_CHARS else summary[:SUMMARY_CHARS].rsplit(" ", 1)[0] + "…",
            "caveats": row["caveats"],
        })
    cells = db.execute(text("""
        SELECT c.assessment_id, ST_X(c.geometry) AS longitude, ST_Y(c.geometry) AS latitude,
               c.destroyed, c.severe, c.moderate, c.possible, c.unclassified
        FROM damage_cells AS c WHERE c.assessment_id = ANY(:ids)
    """), {"ids": on_map}).mappings().all() if on_map else []
    titles = {a["id"]: (a["title"], a["imagery_date"]) for a in assessments}
    features = []
    for cell in cells:
        counts = {name: cell[name] for name in CLASSES}
        total = sum(counts.values())
        if not total:
            continue
        title, imagery = titles[cell["assessment_id"]]
        features.append({
            "type": "Feature", "geometry": {"type": "Point", "coordinates": [round(cell["longitude"], 4), round(cell["latitude"], 4)]},
            "properties": {**counts, "total": total, "destroyed_share": round(counts["destroyed"] / total, 2),
                           "assessment": title, "imagery_date": imagery},
        })
    shown = [a for a in assessments if a["on_map"]]
    return {
        "assessments": assessments,
        "cells": {"type": "FeatureCollection", "features": features},
        "totals_on_map": {name: sum((a["counts"] or {}).get(name) or 0 for a in shown) for name in CLASSES},
        "cell_km": round(CELL_DEGREES * 111, 1), "country": country, "generated_at": now.isoformat(),
        "attribution": ATTRIBUTION, "caveats": CAVEATS, "transformation": TRANSFORMATION,
    }
