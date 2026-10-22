"""UNOSAT satellite damage assessments for MENA, from the Humanitarian Data Exchange.

Source: United Nations Satellite Centre (UNOSAT), published on HDX
(https://data.humdata.org/organization/unosat). Licence per dataset, recorded as
published (UNOSAT uses Creative Commons Attribution Share-Alike). MCHO keeps the
catalogue entry and, where the geodata can be read, counts damaged structures by
UNOSAT's own damage class in ~500 m grid cells. That grid is a stated
transformation and is shared under the same licence. Individual structures are
not stored or shown.

Only conflict assessments are kept: UNOSAT "complex emergency" activations (codes
starting CE) whose title is about damage to structures. Floods, earthquakes,
cropland, roads and density summaries are left out.
"""
import logging
import re
import tempfile
import threading
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.entities import DamageAssessment, DamageRefresh, utcnow

logger = logging.getLogger("mcho.damage")

HDX_SEARCH = "https://data.humdata.org/api/3/action/package_search"
HDX_DATASET = "https://data.humdata.org/dataset/"
DOWNLOAD_HOSTS = ("unosat.org", "www.unosat.org", "cern.ch", "unosat-maps.web.cern.ch", "data.humdata.org")
MAX_DOWNLOAD_BYTES = 25_000_000
MAX_FILES_PER_REFRESH = 6
CELL_DEGREES = 0.005  # ~500 m
INSERT_CHUNK = 20_000
REFRESH_HOURS = 24
RETRY_AFTER_FAILURE = timedelta(hours=1)
REFRESH_LOCK_KEY = 4_216_003
ATTRIBUTION = "Source: United Nations Satellite Centre (UNOSAT), via the Humanitarian Data Exchange (HDX)"
CLASSES = ("destroyed", "severe", "moderate", "possible", "unclassified")

_DAMAGE_TITLE = re.compile(r"damage|destr", re.I)
_EXCLUDED_TITLE = re.compile(r"flood|water|surge|crop|agricult|greenhouse|road|density|percentage|environment|oil fire|earthquake", re.I)
_UNOSAT_CODE = re.compile(r"\b(CE\d{8}[A-Z]{3})\b")
_EXCLUDED_LAYER = re.compile(r"density|road|crop|agri|greenhouse|aoi|boundar|extent|grid|fras_", re.I)
_DAMAGE_LAYER = re.compile(r"damage|_da_|_da$|cda|site", re.I)
_process_lock = threading.Lock()


class UnosatError(RuntimeError):
    """A failure with a message safe to store and show."""


def damage_class(value: Any) -> str | None:
    """Map a UNOSAT damage value (numeric code or label) to a class; None = no damage / other."""
    if value is None:
        return None
    try:
        code = float(value)
    except (TypeError, ValueError):
        label = str(value).strip().lower()
        for name in ("destroyed", "severe", "moderate", "possible"):
            if label.startswith(name):
                return name
        return None
    if code != code:  # NaN
        return None
    return {1: "destroyed", 2: "severe", 3: "moderate", 4: "possible", 11: "possible"}.get(int(code))


def _numbered(fields: list[str], pattern: str) -> list[str]:
    """Fields matching ``pattern`` (with an optional _N suffix), oldest first."""
    found = []
    for field in fields:
        match = re.fullmatch(pattern + r"(?:_(\d+))?", field, re.I)
        if match:
            found.append((int(match.group(1) or 0), field))
    return [field for _, field in sorted(found)]


def class_fields(fields: list[str]) -> list[str]:
    """UNOSAT damage-class columns, oldest assessment date first."""
    return _numbered(fields, "Main_Damage_Site_Class") or _numbered(fields, "Main_Dam") or _numbered(fields, "Main_Damag")


def date_fields(fields: list[str]) -> list[str]:
    """Imagery date columns, including shapefile-truncated names such as SensorDa_1."""
    return _numbered(fields, "SensorDate") + _numbered(fields, "SensorDa") + _numbered(fields, "Date")


def _as_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def srid_for(crs: str | None) -> int | None:
    """PostGIS SRID for a layer CRS; WGS 84 with a vertical datum counts as 4326."""
    if not crs:
        return None
    match = re.fullmatch(r"EPSG:(\d+)", crs.strip())
    if match:
        code = int(match.group(1))
        return 4326 if code in (4326, 4979, 9707) else code
    if "PROJCS" not in crs and "PROJCRS" not in crs and 'GEOGCS["WGS 84"' in crs:
        return 4326
    return None


def _sources(archive: Path) -> list[str]:
    names = zipfile.ZipFile(archive).namelist()
    gdbs = {name.split(".gdb/")[0] + ".gdb" for name in names if ".gdb/" in name}
    return sorted(gdbs | {name for name in names if name.lower().endswith(".shp")})


def read_damage_points(archive: Path) -> dict[str, Any]:
    """Pick the damage layer in a UNOSAT zip and return points with their class.

    The layer with the latest imagery date wins (UNOSAT files often keep earlier
    snapshots of the same area as separate layers). For each structure the most
    recent non-empty damage-class column is used. Layers without a class column
    are used only when their name says they hold damage sites; their structures
    count as damaged, class not given.
    """
    import numpy as np
    import pyogrio
    import pyogrio.raw
    import shapely

    candidates = []
    for source in _sources(archive):
        path = f"/vsizip/{archive}/{source}"
        try:
            layers = pyogrio.list_layers(path)
        except Exception:  # noqa: BLE001 - unreadable member: try the others
            continue
        for name, geometry_type in layers:
            if geometry_type is None or _EXCLUDED_LAYER.search(name):
                continue
            info = pyogrio.read_info(path, layer=name)
            fields = list(info["fields"])
            classes, dates = class_fields(fields), date_fields(fields)
            if not classes and not _DAMAGE_LAYER.search(name):
                continue
            if info["features"] == 0:
                continue
            _, _, _, values = pyogrio.raw.read(path, layer=name, read_geometry=False, columns=dates) if dates else (None, None, None, [])
            seen = [d for column in values for d in map(_as_date, column.tolist()) if d]
            candidates.append((max(seen) if seen else date.min, info["features"], path, name, classes, info["crs"]))
    if not candidates:
        raise UnosatError("No damage-site layer found in the UNOSAT file.")
    imagery, _, path, name, classes, crs = max(candidates, key=lambda c: (c[0], c[1]))
    srid = srid_for(crs)
    if srid is None:
        raise UnosatError("Unsupported coordinate system in the UNOSAT file.")
    _, _, geometry, values = pyogrio.raw.read(path, layer=name, columns=classes)
    shapes = shapely.from_wkb(geometry)
    present = ~(shapely.is_missing(shapes) | shapely.is_empty(shapes))
    xs, ys = np.full(len(shapes), np.nan), np.full(len(shapes), np.nan)
    points = shapely.point_on_surface(shapes[present])
    xs[present], ys[present] = shapely.get_x(points), shapely.get_y(points)
    if classes:
        labels: list[str | None] = [None] * len(xs)
        for column in values:  # later columns overwrite earlier ones where present
            for i, raw_value in enumerate(column.tolist()):
                if raw_value is not None and raw_value == raw_value and str(raw_value).strip() != "":
                    labels[i] = damage_class(raw_value) or "none"
        labels = [None if label == "none" else label for label in labels]
    else:
        labels = ["unclassified"] * len(xs)
    keep = [i for i, label in enumerate(labels) if label and np.isfinite(xs[i]) and np.isfinite(ys[i])]
    return {
        "layer": name, "srid": srid, "imagery_date": imagery if imagery != date.min else None,
        "x": [float(xs[i]) for i in keep], "y": [float(ys[i]) for i in keep], "class": [labels[i] for i in keep],
    }


_INSERT_CELLS = text("""
    INSERT INTO damage_cells (assessment_id, cell_x, cell_y, geometry, destroyed, severe, moderate, possible, unclassified)
    SELECT :aid, cx, cy, ST_SetSRID(ST_MakePoint((cx + 0.5) * :cell, (cy + 0.5) * :cell), 4326),
           count(*) FILTER (WHERE cls = 'destroyed'), count(*) FILTER (WHERE cls = 'severe'),
           count(*) FILTER (WHERE cls = 'moderate'), count(*) FILTER (WHERE cls = 'possible'),
           count(*) FILTER (WHERE cls = 'unclassified')
    FROM (
        SELECT floor(ST_X(g) / :cell)::int AS cx, floor(ST_Y(g) / :cell)::int AS cy, cls
        FROM (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(x, y), :srid), 4326) AS g, cls
              FROM unnest(CAST(:xs AS double precision[]), CAST(:ys AS double precision[]), CAST(:classes AS text[])) AS u(x, y, cls)) AS t
        WHERE ST_Y(g) BETWEEN -90 AND 90 AND ST_X(g) BETWEEN -180 AND 180
    ) AS s
    GROUP BY cx, cy
    ON CONFLICT (assessment_id, cell_x, cell_y) DO UPDATE SET
        destroyed = damage_cells.destroyed + EXCLUDED.destroyed, severe = damage_cells.severe + EXCLUDED.severe,
        moderate = damage_cells.moderate + EXCLUDED.moderate, possible = damage_cells.possible + EXCLUDED.possible,
        unclassified = damage_cells.unclassified + EXCLUDED.unclassified
""")


def store_cells(db: Session, assessment_id: str, points: dict[str, Any]) -> dict[str, int]:
    db.execute(text("DELETE FROM damage_cells WHERE assessment_id = :aid"), {"aid": assessment_id})
    for start in range(0, len(points["x"]), INSERT_CHUNK):
        end = start + INSERT_CHUNK
        db.execute(_INSERT_CELLS, {"aid": assessment_id, "cell": CELL_DEGREES, "srid": points["srid"],
                                   "xs": points["x"][start:end], "ys": points["y"][start:end], "classes": points["class"][start:end]})
    totals = db.execute(text("""
        SELECT coalesce(sum(destroyed), 0) AS destroyed, coalesce(sum(severe), 0) AS severe, coalesce(sum(moderate), 0) AS moderate,
               coalesce(sum(possible), 0) AS possible, coalesce(sum(unclassified), 0) AS unclassified
        FROM damage_cells WHERE assessment_id = :aid
    """), {"aid": assessment_id}).mappings().one()
    db.execute(text("""
        UPDATE damage_assessments SET extent = (
            SELECT ST_Envelope(ST_Buffer(ST_Collect(geometry), :half, 'quad_segs=1')) FROM damage_cells WHERE assessment_id = :aid)
        WHERE id = :aid
    """), {"aid": assessment_id, "half": CELL_DEGREES / 2})
    return {name: int(totals[name]) for name in CLASSES}


def eligible(package: dict[str, Any]) -> bool:
    title = package.get("title") or ""
    if not _DAMAGE_TITLE.search(title) or _EXCLUDED_TITLE.search(title):
        return False
    return unosat_code(package) is not None


def unosat_code(package: dict[str, Any]) -> str | None:
    texts = [package.get("notes") or ""] + [r.get("url") or "" for r in package.get("resources") or []]
    for value in texts:
        match = _UNOSAT_CODE.search(value)
        if match:
            return match.group(1)
    return None


def pick_resource(package: dict[str, Any]) -> str | None:
    """A zipped geodatabase or shapefile within the size limit, geodatabase first."""
    ranked = []
    for resource in package.get("resources") or []:
        url, fmt, size = resource.get("url") or "", (resource.get("format") or "").lower(), resource.get("size")
        host = urlsplit(url).hostname or ""
        if not url.lower().endswith(".zip") or host not in DOWNLOAD_HOSTS:
            continue
        if isinstance(size, (int, float)) and size > MAX_DOWNLOAD_BYTES:
            continue
        if fmt in ("geodatabase", "shp", "zipped shapefile", "zipped geodatabase"):
            ranked.append((0 if "geodatabase" in fmt else 1, url))
    return min(ranked)[1] if ranked else None


def _published(package: dict[str, Any]) -> date | None:
    match = re.search(r"\d{4}-\d{2}-\d{2}", package.get("dataset_date") or "")
    return date.fromisoformat(match.group(0)) if match else None


def fetch_catalogue(client: httpx.Client, countries: list[str]) -> list[dict[str, Any]]:
    groups = " OR ".join(code.lower() for code in countries)
    params = {"q": f"organization:unosat AND groups:({groups})", "rows": 1000, "sort": "metadata_modified desc"}
    try:
        response = client.get(HDX_SEARCH, params=params, timeout=httpx.Timeout(60.0, connect=10.0))
    except httpx.HTTPError as exc:
        raise UnosatError(f"HDX request failed ({type(exc).__name__}).") from None
    if response.status_code != 200:
        raise UnosatError(f"HDX returned HTTP {response.status_code}.")
    try:
        result = response.json()["result"]
    except (ValueError, KeyError, TypeError):
        raise UnosatError("HDX returned an unexpected response.") from None
    return [p for p in result.get("results") or [] if isinstance(p, dict) and eligible(p)]


def download(client: httpx.Client, url: str, target: Path) -> None:
    """Stream a file from an allowed host, refusing anything over the size limit."""
    current = url
    for _ in range(4):  # follow at most a few redirects, each to an allowed host
        if (urlsplit(current).hostname or "") not in DOWNLOAD_HOSTS or urlsplit(current).scheme != "https":
            raise UnosatError("Download host not allowed.")
        try:
            with client.stream("GET", current, timeout=httpx.Timeout(120.0, connect=10.0)) as response:
                if response.status_code in (301, 302, 303, 307, 308) and response.headers.get("location"):
                    current = str(response.url.join(response.headers["location"]))
                    continue
                if response.status_code != 200:
                    raise UnosatError(f"UNOSAT file returned HTTP {response.status_code}.")
                written = 0
                with target.open("wb") as out:
                    for chunk in response.iter_bytes():
                        written += len(chunk)
                        if written > MAX_DOWNLOAD_BYTES:
                            raise UnosatError("UNOSAT file is larger than the processing limit.")
                        out.write(chunk)
                return
        except httpx.HTTPError as exc:
            raise UnosatError(f"UNOSAT download failed ({type(exc).__name__}).") from None
    raise UnosatError("Too many redirects for the UNOSAT file.")


def needs_refresh(db: Session, now: datetime | None = None) -> bool:
    now = now or utcnow()
    last_success = db.scalar(select(func.max(DamageRefresh.finished_at)).where(DamageRefresh.status == "succeeded"))
    pending = db.scalar(select(func.count()).select_from(DamageAssessment).where(DamageAssessment.status == "pending"))
    if last_success and last_success > now - timedelta(hours=REFRESH_HOURS) and not pending:
        return False
    last_attempt = db.scalar(select(func.max(DamageRefresh.started_at)))
    retry = RETRY_AFTER_FAILURE if not pending else timedelta(minutes=10)
    return not (last_attempt and last_attempt > now - retry)


def _upsert_catalogue(db: Session, packages: list[dict[str, Any]], countries: set[str], now: datetime) -> None:
    newest_by_file: dict[str, dict[str, Any]] = {}
    for package in packages:
        url = pick_resource(package)
        if url and (url not in newest_by_file or (_published(package) or date.min) > (_published(newest_by_file[url]) or date.min)):
            newest_by_file[url] = package
    for package in packages:
        codes = [g.get("name", "").upper() for g in package.get("groups") or []]
        country = next((code for code in codes if code in countries), None)
        url = pick_resource(package)
        existing = db.get(DamageAssessment, package["id"])
        if url is None:
            status, detail = "catalogue", "No geodata file small enough to process; see the dataset on HDX."
        elif newest_by_file[url]["id"] != package["id"]:
            status, detail = "catalogue", f"Same data file as the newer entry \"{newest_by_file[url]['title']}\"."
        elif existing and existing.resource_url == url and existing.status in ("mapped", "failed"):
            status, detail = existing.status, existing.status_detail
        else:
            status, detail = "pending", None
        values = {
            "name": package.get("name") or package["id"], "title": package.get("title") or "Untitled",
            "country_code": country, "unosat_code": unosat_code(package), "published_on": _published(package),
            "resource_url": url, "licence": package.get("license_title") or "Licence not stated",
            "licence_url": package.get("license_url"), "summary": (package.get("notes") or "").strip()[:4000],
            "caveats": (package.get("caveats") or "").strip()[:2000] or None, "status": status, "status_detail": detail,
            "updated_at": now,
        }
        if existing is None:
            db.add(DamageAssessment(id=package["id"], **values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
            if status == "catalogue":
                db.execute(text("DELETE FROM damage_cells WHERE assessment_id = :aid"), {"aid": package["id"]})
                existing.extent = None
                for name in CLASSES:
                    setattr(existing, name, None)


def refresh_damage(db: Session, client: httpx.Client, now: datetime | None = None,
                   reader: Callable[[Path], dict[str, Any]] = read_damage_points) -> DamageRefresh | None:
    """Sync the catalogue, then process a few pending files with no transaction held during downloads."""
    now = now or utcnow()
    wall_start = utcnow()
    if not db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": REFRESH_LOCK_KEY}) or not needs_refresh(db, now):
        db.rollback()
        return None
    refresh = DamageRefresh(started_at=now, status="running")
    db.add(refresh)
    db.commit()
    refresh_id = refresh.id
    mapped = 0
    try:
        countries = [code for (code,) in db.execute(text("SELECT iso_a3 FROM country_boundaries ORDER BY iso_a3")).all()]
        db.commit()
        packages = fetch_catalogue(client, countries)
        _upsert_catalogue(db, packages, set(countries), now)
        db.commit()
        pending = db.execute(select(DamageAssessment.id, DamageAssessment.resource_url).where(DamageAssessment.status == "pending")
                             .order_by(DamageAssessment.published_on.desc().nullslast()).limit(MAX_FILES_PER_REFRESH)).all()
        db.commit()
        for assessment_id, url in pending:
            mapped += _process_one(db, client, assessment_id, url, reader)
        refresh = db.get(DamageRefresh, refresh_id)
        refresh.status, refresh.rows_stored = "succeeded", mapped
        refresh.finished_at = now + (utcnow() - wall_start)
        db.commit()
        logger.info("damage_refresh_succeeded catalogue=%s mapped=%s", len(packages), mapped)
    except Exception as exc:
        db.rollback()
        refresh = db.get(DamageRefresh, refresh_id)
        refresh.status, refresh.rows_stored = "failed", mapped
        refresh.error_summary = str(exc) if isinstance(exc, UnosatError) else f"{type(exc).__name__}: refresh stopped."
        refresh.finished_at = now + (utcnow() - wall_start)
        db.commit()
        logger.warning("damage_refresh_failed error_type=%s summary=%s", type(exc).__name__, refresh.error_summary)
        if not isinstance(exc, UnosatError):
            raise
    return refresh


def _process_one(db: Session, client: httpx.Client, assessment_id: str, url: str,
                 reader: Callable[[Path], dict[str, Any]]) -> bool:
    """Download and grid one assessment; a bad file marks only that assessment as failed."""
    try:
        with tempfile.TemporaryDirectory(prefix="unosat-") as folder:
            archive = Path(folder) / "assessment.zip"
            download(client, url, archive)
            try:
                points = reader(archive)
            except UnosatError:
                raise
            except Exception as exc:  # noqa: BLE001 - any unreadable file is that file's problem
                raise UnosatError(f"Could not read the UNOSAT file ({type(exc).__name__}).") from None
        if not points["x"]:
            raise UnosatError("The file contains no damaged structures in a recognised UNOSAT class.")
    except UnosatError as exc:
        assessment = db.get(DamageAssessment, assessment_id)
        assessment.status, assessment.status_detail, assessment.processed_at = "failed", str(exc), utcnow()
        db.commit()
        logger.warning("damage_file_failed assessment=%s summary=%s", assessment_id, exc)
        return False
    totals = store_cells(db, assessment_id, points)
    assessment = db.get(DamageAssessment, assessment_id)
    assessment.status, assessment.status_detail = "mapped", f"Layer {points['layer']}"
    assessment.imagery_date = points["imagery_date"]
    assessment.processed_at = utcnow()
    for name, value in totals.items():
        setattr(assessment, name, value)
    db.commit()
    return True


def refresh_in_background() -> None:
    if not _process_lock.acquire(blocking=False):
        return
    from app.db.session import SessionLocal

    try:
        with SessionLocal() as db, httpx.Client(follow_redirects=False, headers={"User-Agent": "MCHO observatory (non-commercial)"}) as client:
            refresh_damage(db, client)
    except Exception:
        logger.exception("damage_refresh_crashed")
    finally:
        _process_lock.release()
