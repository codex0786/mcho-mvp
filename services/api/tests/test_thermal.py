import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import engine, get_db
from app.main import app
from app.models.entities import ThermalDetection, ThermalRefresh
from app.thermal.analysis import detections_geojson, insights
from app.thermal.firms import FirmsError, build_area_url, fetch_csv, parse_csv
from app.thermal.refresh import refresh_thermal

KEY = "a" * 32
HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight"


def _csv(*rows: str) -> str:
    return "\n".join([HEADER, *rows]) + "\n"


# ---------------------------------------------------------------- unit tests

def test_parse_csv_keeps_valid_rows_and_rejects_malformed_ones():
    text_body = _csv(
        "15.5501,32.5301,345.2,0.39,0.36,2026-10-20,0142,N,VIIRS,n,2.0NRT,290.1,12.4,N",
        "33.5,36.3,330.0,0.4,0.4,2026-10-20,5,N20,VIIRS,h,2.0NRT,288.0,3.1,D",
        "95.0,32.5,345.2,0.39,0.36,2026-10-20,0142,N,VIIRS,n,2.0NRT,290.1,12.4,N",
        "15.5,32.5,345.2,0.39,0.36,2026-10-20,25:00,N,VIIRS,n,2.0NRT,290.1,12.4,N",
        "15.5,32.5,345.2,0.39,0.36,2026-10-20,0142,N,VIIRS,n,2.0NRT,290.1,12.4,X",
    )
    rows, rejected = parse_csv(text_body, "VIIRS_SNPP_NRT")
    assert rejected == 3
    assert [row["acquired_at"] for row in rows] == ["2026-10-20T01:42:00+00:00", "2026-10-20T00:05:00+00:00"]
    assert rows[0]["frp"] == 12.4 and rows[0]["confidence"] == "n" and rows[0]["latitude"] == 15.5501
    assert rows[1]["satellite"] == "N20" and rows[1]["daynight"] == "D"


def test_area_url_validates_inputs_and_supports_backfill_dates():
    url = build_area_url(KEY, "VIIRS_NOAA20_NRT", "-18,8,64,40", 5, datetime(2026, 10, 11).date())
    assert url.endswith(f"/{KEY}/VIIRS_NOAA20_NRT/-18,8,64,40/5/2026-10-11")
    assert "/VIIRS_SNPP_SP/" in build_area_url(KEY, "VIIRS_SNPP_SP", "-18,8,64,40", 5, datetime(2025, 10, 1).date())
    for bad in [("bad/key", "VIIRS_SNPP_NRT", 1), (KEY, "LANDSAT_NRT", 1), (KEY, "VIIRS_SNPP_NRT", 6)]:
        with pytest.raises(FirmsError):
            build_area_url(bad[0], bad[1], "-18,8,64,40", bad[2])


def test_fetch_errors_never_include_the_key():
    url = build_area_url(KEY, "VIIRS_SNPP_NRT", "-18,8,64,40", 1)
    responses = {
        "invalid": httpx.Response(200, text="Invalid MAP_KEY."),
        "server": httpx.Response(503, text="down"),
    }
    for name, response in responses.items():
        client = httpx.Client(transport=httpx.MockTransport(lambda request, r=response: r))
        with pytest.raises(FirmsError) as exc:
            fetch_csv(client, url)
        assert KEY not in str(exc.value), name
    ok = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=_csv())))
    assert fetch_csv(ok, url).startswith("latitude,")


def test_thermal_endpoints_validate_bbox_without_touching_data():
    client = TestClient(app)
    assert client.get("/api/v1/thermal/detections?west=10&south=5&east=0&north=6").status_code == 400
    assert client.get("/api/v1/thermal/insights?hours=200").status_code == 422


# ------------------------------------------------------- PostGIS integration

@pytest.fixture
def db():
    if os.getenv("MCHO_INTEGRATION_TESTS") != "1":
        pytest.skip("Set MCHO_INTEGRATION_TESTS=1 to run PostgreSQL/PostGIS integration tests.")
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        session.execute(text("DELETE FROM thermal_detections"))
        session.execute(text("DELETE FROM thermal_refreshes"))
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _add(db, lat, lon, when, country, frp=5.0, satellite="N"):
    db.add(ThermalDetection(
        product="VIIRS_SNPP_NRT", satellite=satellite, instrument="VIIRS", acquired_at=when,
        latitude=lat, longitude=lon, geometry=WKTElement(f"POINT({lon} {lat})", srid=4326),
        country_code=country, frp=frp, confidence="n", daynight="N", version="2.0NRT",
    ))


def test_migration_loads_mena_borders(db):
    count = db.scalar(text("SELECT count(*) FROM country_boundaries"))
    assert count == 22
    khartoum = db.scalar(text(
        "SELECT iso_a3 FROM country_boundaries WHERE ST_Intersects(geometry, ST_SetSRID(ST_MakePoint(32.53, 15.55), 4326))"
    ))
    assert khartoum == "SDN"


def test_refresh_stores_in_region_detections_once_and_is_throttled(db, monkeypatch):
    monkeypatch.setattr(settings, "nasa_firms_api_key", KEY)
    now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
    body = _csv(
        "15.5501,32.5301,345.2,0.39,0.36,2026-10-21,0142,N,VIIRS,n,2.0NRT,290.1,12.4,N",  # Sudan
        "33.5100,36.3000,330.0,0.40,0.40,2026-10-21,0005,N,VIIRS,h,2.0NRT,288.0,3.1,N",   # Syria
        "26.5000,52.0000,330.0,0.40,0.40,2026-10-21,0005,N,VIIRS,h,2.0NRT,288.0,3.1,N",   # Gulf, offshore
    )
    requests = []

    def handler(request):
        requests.append(request.url.path.replace(KEY, "KEY"))
        # Each product is a different satellite; only Suomi NPP saw these fires.
        return httpx.Response(200, text=body if "/VIIRS_SNPP_NRT/" in request.url.path else _csv())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    first = refresh_thermal(db, client, now)
    assert first.status == "succeeded"
    assert len(requests) == 6 and sum(path.endswith("/5") for path in requests) == 3  # backfill: 2 windows x 3 products
    assert first.rows_stored == 2  # the offshore detection has no country and is not stored
    assert dict(db.execute(select(ThermalDetection.country_code, func.count()).group_by(ThermalDetection.country_code)).all()) == {"SDN": 1, "SYR": 1}

    assert refresh_thermal(db, client, now + timedelta(minutes=5)) is None  # throttled

    later = refresh_thermal(db, client, now + timedelta(hours=1))
    assert later.status == "succeeded" and later.rows_stored == 0  # idempotent
    assert all(path.endswith("/2") for path in requests[6:]) and len(requests) == 9


def test_refresh_failure_is_recorded_without_the_key(db, monkeypatch):
    monkeypatch.setattr(settings, "nasa_firms_api_key", KEY)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="Invalid MAP_KEY.")))
    result = refresh_thermal(db, client, datetime(2026, 10, 21, 12, tzinfo=timezone.utc))
    assert result.status == "failed" and KEY not in (result.error_summary or "")
    assert db.scalar(select(func.count()).select_from(ThermalRefresh).where(ThermalRefresh.status == "failed")) == 1


def test_analysis_separates_new_recurring_and_persistent_activity(db):
    now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
    for day in range(2, 7):  # Iraq gas flare: five baseline days, one in window
        _add(db, 30.5001, 47.5001, now - timedelta(days=day), "IRQ")
    _add(db, 30.5002, 47.5002, now - timedelta(hours=3), "IRQ")
    for day in (3, 5):  # Syria: two baseline days, one in window
        _add(db, 35.0001, 38.0001, now - timedelta(days=day), "SYR")
    _add(db, 35.0002, 38.0002, now - timedelta(hours=5), "SYR")
    for i in range(12):  # Sudan: twelve new detections in one ~10 km area
        _add(db, 15.55 + i * 0.004, 32.53 + i * 0.004, now - timedelta(hours=1 + i), "SDN", frp=20.0 + i, satellite="N20" if i % 2 else "N")
    db.commit()

    result = insights(db, now)
    by_country = {item["iso_a3"]: item for item in result["countries"]}
    assert by_country["SDN"]["active_detections"] == 12 and by_country["SDN"]["new_detections"] == 12
    assert by_country["SDN"]["elevated"] is True
    assert by_country["IRQ"]["persistent_detections"] == 1 and by_country["IRQ"]["active_detections"] == 0
    assert by_country["SYR"]["active_detections"] == 1 and by_country["SYR"]["elevated"] is False
    assert by_country["SYR"]["baseline_daily_average"] == round(2 / 7, 1)
    assert result["new_activity_clusters"][0]["country_code"] == "SDN"
    assert result["new_activity_clusters"][0]["detections"] >= 2
    assert result["totals"]["elevated_countries"] == 1

    features = detections_geojson(db, now, 24, (20, 10, 60, 40))["features"]
    classes = {(f["properties"]["country_code"], f["properties"]["classification"]) for f in features}
    assert {("IRQ", "persistent"), ("SYR", "recurring"), ("SDN", "new")} <= classes


def test_public_endpoints_report_freshness_and_do_not_refresh_without_a_key(db, monkeypatch):
    monkeypatch.setattr(settings, "nasa_firms_api_key", "")
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        payload = client.get("/api/v1/thermal/insights").json()
        assert payload["freshness"]["configured"] is False and payload["freshness"]["refresh_scheduled"] is False
        assert "not a verified event" in payload["caveats"]
        geo = client.get("/api/v1/thermal/detections?west=-18&south=8&east=64&north=40").json()
        assert geo["type"] == "FeatureCollection" and geo["truncated"] is False
    finally:
        app.dependency_overrides.clear()


def test_capped_map_keeps_new_activity_before_persistent_sites(db, monkeypatch):
    now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
    for site in range(3):  # three flare sites: five baseline days each, plus very recent window detections
        lat, lon = 30.5 + site * 0.3, 47.5 + site * 0.3
        for day in range(2, 7):
            _add(db, lat, lon, now - timedelta(days=day), "IRQ")
        _add(db, lat, lon, now - timedelta(minutes=10 + site), "IRQ")
    for i in range(2):  # two new detections, older than every flare detection in the window
        _add(db, 15.55 + i * 0.05, 32.53, now - timedelta(hours=20 + i), "SDN")
    db.commit()

    monkeypatch.setattr("app.thermal.analysis.MAX_FEATURES", 2)
    result = detections_geojson(db, now, 24, (20, 10, 60, 40))
    assert result["truncated"] is True
    assert [f["properties"]["classification"] for f in result["features"]] == ["new", "new"]


def test_country_list_has_bounds_for_navigation(db):
    from app.thermal.analysis import country_list

    countries = {c["iso_a3"]: c for c in country_list(db)}
    assert len(countries) == 22
    west, south, east, north = countries["SDN"]["bbox"]
    assert 21 < west < 25 and 8 < south < 10 and 37 < east < 40 and 21 < north < 24
    assert countries["SDN"]["name"] == "Sudan"


def test_country_trend_splits_persistent_sites_and_marks_missing_days(db):
    from app.thermal.analysis import country_trend

    now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
    for day in range(1, 9):  # a flare site in Sudan with heat every day for 8 days (start of data)
        _add(db, 12.0001, 30.0001, now - timedelta(days=day), "SDN")
    for day in (2, 3):  # other activity on two days
        for i in range(3):
            _add(db, 14.0 + i * 0.1, 31.0, now - timedelta(days=day, hours=i), "SDN")
    _add(db, 14.5, 31.5, now - timedelta(hours=2), "SDN")  # today, partial
    db.commit()

    trend = country_trend(db, now, "SDN", 21)
    series = {point["date"]: point for point in trend["series"]}
    assert len(trend["series"]) == 22
    assert series["2026-10-01"]["covered"] is False and series["2026-10-01"]["total"] is None  # before data began
    assert series["2026-10-13"]["covered"] is False  # first, partial day of collection
    day2 = series["2026-10-19"]
    assert day2["covered"] is True and day2["total"] == 4 and day2["persistent"] == 1 and day2["other"] == 3
    today = series["2026-10-21"]
    assert today["partial"] is True and today["other"] == 1


def test_country_filters_and_unknown_countries(db, monkeypatch):
    monkeypatch.setattr(settings, "nasa_firms_api_key", "")
    now = datetime.now(timezone.utc)
    for i in range(3):
        _add(db, 15.55 + i * 0.01, 32.53, now - timedelta(hours=1 + i), "SDN")
        _add(db, 35.0 + i * 0.01, 38.0, now - timedelta(hours=1 + i), "SYR")
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        geo = client.get("/api/v1/thermal/detections?west=-18&south=8&east=64&north=40&country=SYR").json()
        assert {f["properties"]["country_code"] for f in geo["features"]} == {"SYR"}
        clusters = client.get("/api/v1/thermal/insights?country=SDN").json()["new_activity_clusters"]
        assert clusters and {c["country_code"] for c in clusters} == {"SDN"}
        assert client.get("/api/v1/thermal/countries").json()["items"][0]["iso_a3"]
        assert client.get("/api/v1/thermal/countries/SDN/trend?days=7").json()["iso_a3"] == "SDN"
        assert client.get("/api/v1/thermal/countries/FRA/trend").status_code == 404
        assert client.get("/api/v1/thermal/insights?country=sdn").status_code == 422
    finally:
        app.dependency_overrides.clear()
