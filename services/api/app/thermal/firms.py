"""NASA FIRMS area API client and CSV parsing.

FIRMS publishes satellite fire/thermal-anomaly detections. Each row is a heat
signature at a ~375 m VIIRS pixel; it is an observation, not a verified event.
API reference: https://firms.modaps.eosdis.nasa.gov/api/area/
"""
import csv
import io
import re
from datetime import date, datetime, timezone
from typing import Any

import httpx

FIRMS_AREA_CSV = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
NRT_PRODUCTS = frozenset({"VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT"})
# Standard-processing archive products, used for last year's comparison.
ARCHIVE_PRODUCTS = frozenset({"VIIRS_SNPP_SP", "VIIRS_NOAA20_SP", "VIIRS_NOAA21_SP", "MODIS_SP"})
SATELLITE_NAMES = {"N": "Suomi NPP", "N20": "NOAA-20", "N21": "NOAA-21", "Terra": "Terra", "Aqua": "Aqua", "T": "Terra", "A": "Aqua"}
_MAP_KEY = re.compile(r"^[A-Za-z0-9]{16,64}$")
MAX_DAY_RANGE = 5


class FirmsError(RuntimeError):
    """A FIRMS failure whose message is safe to store and show (never contains the key)."""


def parse_area(value: str) -> tuple[float, float, float, float]:
    try:
        west, south, east, north = (float(part) for part in value.split(","))
    except ValueError as exc:
        raise ValueError("FIRMS area must be 'west,south,east,north' in degrees.") from exc
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("FIRMS area is outside valid longitude/latitude bounds.")
    return west, south, east, north


def build_area_url(map_key: str, product: str, area: str, day_range: int, start: date | None = None) -> str:
    if not _MAP_KEY.fullmatch(map_key):
        raise FirmsError("The FIRMS MAP_KEY is not in the expected format.")
    if product not in NRT_PRODUCTS | ARCHIVE_PRODUCTS:
        raise FirmsError(f"Unsupported FIRMS product: {product}.")
    if not 1 <= day_range <= MAX_DAY_RANGE:
        raise FirmsError(f"FIRMS day range must be 1-{MAX_DAY_RANGE}.")
    west, south, east, north = parse_area(area)
    url = f"{FIRMS_AREA_CSV}/{map_key}/{product}/{west:g},{south:g},{east:g},{north:g}/{day_range}"
    return f"{url}/{start.isoformat()}" if start else url


def fetch_csv(client: httpx.Client, url: str) -> str:
    """GET a FIRMS CSV. Errors never include the URL, which contains the key."""
    try:
        response = client.get(url, timeout=httpx.Timeout(60.0, connect=10.0))
    except httpx.HTTPError as exc:
        raise FirmsError(f"FIRMS request failed ({type(exc).__name__}).") from None
    if response.status_code != 200:
        raise FirmsError(f"FIRMS returned HTTP {response.status_code}.")
    text = response.text
    if not text.lstrip().lower().startswith("latitude,"):
        raise FirmsError("FIRMS returned an unexpected response; check that the MAP_KEY is valid.")
    return text


def _float(row: dict[str, str], key: str) -> float | None:
    value = (row.get(key) or "").strip()
    return float(value) if value else None


def parse_csv(text: str, product: str) -> tuple[list[dict[str, Any]], int]:
    """Return (valid rows, rejected count). Malformed rows are dropped, not guessed."""
    rows: list[dict[str, Any]] = []
    rejected = 0
    for raw in csv.DictReader(io.StringIO(text)):
        try:
            latitude = float(raw["latitude"])
            longitude = float(raw["longitude"])
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError("coordinates out of range")
            acq_time = raw["acq_time"].strip().zfill(4)
            if not (acq_time.isdigit() and len(acq_time) == 4):
                raise ValueError("bad acq_time")
            acquired_at = datetime.strptime(f"{raw['acq_date'].strip()} {acq_time}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
            daynight = raw.get("daynight", "").strip().upper()
            if daynight not in {"D", "N"}:
                raise ValueError("bad daynight")
            confidence = raw.get("confidence", "").strip().lower()
            if not confidence or len(confidence) > 10:
                raise ValueError("bad confidence")
            satellite = raw.get("satellite", "").strip()
            rows.append({
                "product": product,
                "satellite": satellite[:20] or "unknown",
                "instrument": (raw.get("instrument") or "VIIRS").strip()[:20],
                "acquired_at": acquired_at.isoformat(),
                "latitude": latitude,
                "longitude": longitude,
                "brightness_ti4": _float(raw, "bright_ti4") if "bright_ti4" in raw else _float(raw, "brightness"),
                "brightness_ti5": _float(raw, "bright_ti5") if "bright_ti5" in raw else _float(raw, "bright_t31"),
                "frp": _float(raw, "frp"),
                "scan": _float(raw, "scan"),
                "track": _float(raw, "track"),
                "confidence": confidence,
                "daynight": daynight,
                "version": (raw.get("version") or "").strip()[:20] or "unknown",
            })
        except (KeyError, ValueError, TypeError):
            rejected += 1
    return rows, rejected
