from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.imagery import sentinel2
from app.imagery.sentinel2 import ImagerySearchError, search_scenes
from app.main import app

NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)


def _feature(scene_id, when, cloud, bbox=(23.0, 9.0, 25.0, 11.0), thumb=True):
    return {
        "id": scene_id, "bbox": list(bbox),
        "properties": {"datetime": when, "eo:cloud_cover": cloud, "grid:code": "MGRS-34PHS"},
        "assets": {"thumbnail": {"href": f"https://sentinel-cogs.s3.us-west-2.amazonaws.com/{scene_id}/preview.jpg"}} if thumb else {},
    }


@pytest.fixture(autouse=True)
def empty_cache():
    sentinel2._cache.clear()
    yield
    sentinel2._cache.clear()


def test_scenes_are_parsed_with_marker_and_clearest_choice():
    bodies = []

    def handler(request):
        bodies.append(request.content)
        return httpx.Response(200, json={"features": [
            _feature("S2_cloudy", "2026-10-19T08:57:42Z", 68.0),
            _feature("S2_clear", "2026-10-14T08:57:42Z", 3.1),
            _feature("S2_no_thumb", "2026-10-12T08:57:42Z", 1.0, thumb=False),
        ]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = search_scenes(client, 10.0, 24.0, 30, NOW)
    assert [s["id"] for s in result["scenes"]] == ["S2_cloudy", "S2_clear"]
    assert result["clearest_recent_id"] == "S2_clear"
    first = result["scenes"][0]
    assert first["marker"] == {"x": 0.5, "y": 0.5} and first["tile"] == "MGRS-34PHS"
    assert first["browser_url"].startswith("https://browser.dataspace.copernicus.eu/?") and "fromTime=2026-10-19" in first["browser_url"]
    assert b'"datetime":"2026-09-21T12:00:00Z/2026-10-21T12:00:00Z"' in bodies[0].replace(b" ", b"")

    # A repeated lookup for the same spot is served from the cache.
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as client:
        assert search_scenes(client, 10.001, 24.001, 30, NOW)["scenes"][1]["id"] == "S2_clear"


def test_catalogue_failures_raise_safe_errors():
    for response in (httpx.Response(503), httpx.Response(200, text="not json")):
        with httpx.Client(transport=httpx.MockTransport(lambda r, resp=response: resp)) as client:
            with pytest.raises(ImagerySearchError):
                search_scenes(client, 15.0, 32.0, 30, NOW)


def test_endpoint_limits_lookups_to_the_covered_area(monkeypatch):
    calls = []
    monkeypatch.setattr("app.routers.sentinel2.search_scenes", lambda client, lat, lon, days: calls.append((lat, lon, days)) or {"scenes": []})
    client = TestClient(app)
    assert client.get("/api/v1/sentinel2/scenes?lat=48.85&lon=2.35").status_code == 400  # Paris
    assert client.get("/api/v1/sentinel2/scenes?lat=10.34&lon=24.14&days=30").status_code == 200
    assert calls == [(10.34, 24.14, 30)]
    assert client.get("/api/v1/sentinel2/scenes?lat=10.34&lon=24.14&days=400").status_code == 422
