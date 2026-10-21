"""Search recent Sentinel-2 L2A scenes over a point via Element 84 Earth Search.

Earth Search (https://earth-search.aws.element84.com/v1) is a free public STAC
API over the Sentinel-2 archive on AWS Open Data. No key is needed. Results are
cached briefly per rounded location so repeated clicks don't hit the catalogue.
"""
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

EARTH_SEARCH_URL = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
CACHE_SECONDS = 3600
MAX_SCENES = 6
_cache: dict[tuple[float, float, int], tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


class ImagerySearchError(RuntimeError):
    """A catalogue failure with a message safe to show."""


def copernicus_browser_link(latitude: float, longitude: float, acquired: datetime) -> str:
    day = acquired.astimezone(timezone.utc).date().isoformat()
    params = {
        "zoom": 13, "lat": f"{latitude:.4f}", "lng": f"{longitude:.4f}", "themeId": "DEFAULT-THEME",
        "datasetId": "S2_L2A_CDAS", "layerId": "1_TRUE_COLOR",
        "fromTime": f"{day}T00:00:00.000Z", "toTime": f"{day}T23:59:59.999Z",
    }
    return f"https://browser.dataspace.copernicus.eu/?{urlencode(params)}"


def _scene(feature: dict[str, Any], latitude: float, longitude: float) -> dict[str, Any] | None:
    properties = feature.get("properties") or {}
    preview = ((feature.get("assets") or {}).get("thumbnail") or {}).get("href")
    bbox = feature.get("bbox")
    try:
        acquired = datetime.fromisoformat(str(properties["datetime"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None
    if not (isinstance(preview, str) and preview.startswith("https://") and isinstance(bbox, list) and len(bbox) == 4):
        return None
    west, south, east, north = (float(v) for v in bbox)
    marker = None
    if west < longitude < east and south < latitude < north:
        # The preview covers the tile's footprint; this lon/lat position is approximate.
        marker = {"x": round((longitude - west) / (east - west), 4), "y": round((north - latitude) / (north - south), 4)}
    cloud = properties.get("eo:cloud_cover")
    return {
        "id": str(feature.get("id")), "acquired_at": acquired.isoformat(),
        "cloud_cover_percent": round(float(cloud), 1) if isinstance(cloud, (int, float)) else None,
        "tile": properties.get("s2:mgrs_tile") or properties.get("grid:code"),
        "preview_url": preview, "bbox": [west, south, east, north], "marker": marker,
        "browser_url": copernicus_browser_link(latitude, longitude, acquired),
    }


def search_scenes(client: httpx.Client, latitude: float, longitude: float, days: int, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    key = (round(latitude, 2), round(longitude, 2), days)
    with _cache_lock:
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
    body = {
        "collections": [COLLECTION],
        "intersects": {"type": "Point", "coordinates": [longitude, latitude]},
        "datetime": f"{(now - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')}/{now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "limit": MAX_SCENES,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
        "fields": {"include": ["id", "bbox", "properties.datetime", "properties.eo:cloud_cover", "properties.s2:mgrs_tile", "properties.grid:code", "assets.thumbnail"]},
    }
    try:
        response = client.post(EARTH_SEARCH_URL, json=body, timeout=httpx.Timeout(20.0, connect=5.0))
    except httpx.HTTPError as exc:
        raise ImagerySearchError(f"The imagery catalogue could not be reached ({type(exc).__name__}).") from None
    if response.status_code != 200:
        raise ImagerySearchError(f"The imagery catalogue returned HTTP {response.status_code}.")
    try:
        features = response.json().get("features") or []
    except ValueError:
        raise ImagerySearchError("The imagery catalogue returned an unexpected response.") from None
    scenes = [scene for scene in (_scene(f, latitude, longitude) for f in features) if scene]
    clear = [s for s in scenes if s["cloud_cover_percent"] is not None and s["cloud_cover_percent"] <= 20]
    result = {
        "latitude": latitude, "longitude": longitude, "days": days, "scenes": scenes,
        "clearest_recent_id": (clear[0] if clear else min(scenes, key=lambda s: s["cloud_cover_percent"] or 100, default=None) or {}).get("id"),
        "source": {"name": "Copernicus Sentinel-2 L2A via Earth Search (Element 84, AWS Open Data)",
                   "url": "https://earth-search.aws.element84.com/v1", "licence": "Copernicus Sentinel data, free and open"},
        "caveats": ("Sentinel-2 is a different satellite from the heat detections: it passes about every 5 days, so an image may "
                    "be from before or after the heat was detected. Previews are low resolution; open the full image at 10 m "
                    "to look for smoke or burn scars. Clouds and smoke can hide the ground. Marker positions are approximate."),
    }
    with _cache_lock:
        if len(_cache) > 500:
            _cache.clear()
        _cache[key] = (time.monotonic(), result)
    return result
