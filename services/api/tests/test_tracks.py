from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.thermal import tracks as tracks_module
from app.thermal.tracks import bearing_degrees, compass, haversine_km, link_clusters, thermal_tracks
from test_thermal import _add, db  # noqa: F401 - shared PostGIS fixture (tests dir is on sys.path)


def _c(day, lon, lat, n=5):
    return {"day": date(2026, 10, day), "longitude": lon, "latitude": lat, "detections": n, "max_frp": 10.0, "country_code": "SDN"}


def test_linking_allows_one_missing_day_but_not_long_jumps():
    tracks = link_clusters([_c(15, 30.0, 12.0), _c(16, 30.1, 12.0), _c(18, 30.2, 12.0), _c(16, 35.0, 15.0), _c(17, 35.5, 15.0)])
    chains = [[(c["day"].day, c["longitude"]) for c in t] for t in tracks]
    assert [(15, 30.0), (16, 30.1), (18, 30.2)] in chains  # the 17th was skipped (e.g. clouds)
    assert [(16, 35.0)] in chains and [(17, 35.5)] in chains  # ~54 km apart: not linked


def test_linking_gives_each_cluster_to_the_closest_track_only_once():
    tracks = link_clusters([_c(15, 30.0, 12.0), _c(15, 30.2, 12.0), _c(16, 30.19, 12.0)])
    joined = [t for t in tracks if len(t) == 2]
    assert len(joined) == 1 and joined[0][0]["longitude"] == 30.2


def test_direction_helpers():
    assert round(haversine_km(30.0, 12.0, 30.2, 12.0), 1) == 21.8
    assert compass(bearing_degrees(30.0, 12.0, 30.2, 12.0)) == "E"
    assert compass(bearing_degrees(30.0, 12.0, 29.9, 11.9)) == "SW"


def test_tracks_follow_a_moving_front_and_ignore_flares(db, monkeypatch):  # noqa: F811
    tracks_module._cache.clear()
    now = datetime(2026, 10, 21, 18, tzinfo=timezone.utc)
    for offset, lon in ((3, 30.00), (2, 30.08), (1, 30.16)):  # a front moving ~9 km east per day
        for i in range(5):
            _add(db, 12.0 + i * 0.01, lon + i * 0.005, now - timedelta(days=offset, hours=i), "SDN", frp=10.0 + i)
    for offset in range(1, 7):  # an Iraqi flare, every day
        for i in range(3):
            _add(db, 30.5 + i * 0.001, 47.5, now - timedelta(days=offset, hours=i), "IRQ")
    db.commit()

    result = thermal_tracks(db, now, 7)
    assert result["total_tracks"] == 1
    track = result["features"][0]["properties"]
    assert track["country_code"] == "SDN" and track["days_active"] == 3 and track["detections"] == 15
    assert track["direction"] == "E" and 15 < track["displacement_km"] < 20
    assert track["active"] is True and track["first_day"] == "2026-10-18" and track["last_day"] == "2026-10-20"
    assert result["features"][0]["geometry"]["type"] == "LineString"
    assert thermal_tracks(db, now, 7, "IRQ")["total_tracks"] == 0

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        assert client.get("/api/v1/thermal/tracks?days=7&country=SDN").json()["type"] == "FeatureCollection"
        assert client.get("/api/v1/thermal/tracks?days=30").status_code == 422
    finally:
        app.dependency_overrides.clear()
