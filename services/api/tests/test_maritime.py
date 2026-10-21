from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import get_db
from app.main import app
from app.maritime.analysis import maritime_overview
from app.maritime.portwatch import (CHOKEPOINT_METRICS, PortWatchError, _metric_rows, query_all, refresh_maritime)
from test_thermal import db  # noqa: F401 - shared PostGIS fixture (tests dir is on sys.path)

NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)


def test_metric_rows_skip_missing_values_and_unknown_areas():
    rows = _metric_rows([
        {"portid": "chokepoint4", "date": "2026-10-18", "n_total": 32, "n_tanker": None, "n_container": 5,
         "n_dry_bulk": 3, "n_cargo": 20, "capacity": 1_000_000},
        {"portid": "chokepoint99", "date": "2026-10-18", "n_total": 7},
        {"portid": "chokepoint4", "date": "not-a-date", "n_total": 1},
    ], CHOKEPOINT_METRICS, {"chokepoint4"})
    metrics = {r["metric"]: r["value"] for r in rows}
    assert "transits_tanker" not in metrics  # missing is not zero
    assert metrics["transits_total"] == 32.0 and metrics["capacity_dwt"] == 1_000_000.0
    assert {r["period_start"] for r in rows} == {"2026-10-18T00:00:00+00:00"}


def test_query_all_follows_arcgis_paging_and_reports_errors():
    calls = []

    def handler(request):
        offset = int(parse_qs(urlsplit(str(request.url)).query)["resultOffset"][0])
        calls.append(offset)
        features = [{"attributes": {"n": offset + i}} for i in range(2 if offset < 4 else 1)]
        return httpx.Response(200, json={"features": features, "exceededTransferLimit": offset < 4})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rows = query_all(client, "https://example.test/Daily_x/query", "1=1", "*")
    assert [r["n"] for r in rows] == [0, 1, 2, 3, 4] and calls == [0, 2, 4]
    for response in (httpx.Response(500), httpx.Response(200, json={"error": {"message": "Invalid query"}})):
        with httpx.Client(transport=httpx.MockTransport(lambda r, resp=response: resp)) as client:
            with pytest.raises(PortWatchError):
                query_all(client, "https://example.test/Daily_x/query", "1=1", "*")


def _fake_portwatch(days):
    """Bab el-Mandeb: 20 transits/day now, 40 a year earlier; Aden port calls: 3/day."""
    def handler(request):
        url = str(request.url)
        if "PortWatch_chokepoints_database" in url:
            feats = [{"attributes": {"portid": "chokepoint4", "portname": "Bab el-Mandeb Strait", "vessel_count_total": 19000},
                      "geometry": {"x": 43.35, "y": 12.79}}]
        elif "PortWatch_ports" in url:
            feats = [{"attributes": {"portid": "port9", "portname": "Aden", "ISO3": "YEM", "vessel_count_total": 400},
                      "geometry": {"x": 44.95, "y": 12.78}}]
        elif "Daily_Chokepoints_Data" in url:
            feats = [{"attributes": {"portid": "chokepoint4", "date": d.isoformat(), "n_total": 20 if d.year == 2026 else 40,
                                     "n_tanker": 5, "n_container": 2, "n_dry_bulk": 4, "n_cargo": 15, "capacity": 900000}} for d in days]
        else:
            feats = [{"attributes": {"portid": "port9", "date": d.isoformat(), "portcalls": 3, "portcalls_tanker": 1,
                                     "portcalls_container": 0, "portcalls_cargo": 2, "import": 5000, "export": 800}} for d in days]
        return httpx.Response(200, json={"features": feats, "exceededTransferLimit": False})
    return handler


def test_refresh_and_overview(db, monkeypatch):  # noqa: F811
    db.execute(text("DELETE FROM maritime_aggregates")); db.execute(text("DELETE FROM maritime_areas")); db.execute(text("DELETE FROM maritime_refreshes"))
    end = date(2026, 10, 18)
    days = [end - timedelta(days=i) for i in range(10)] + [date(2025, 10, 12) + timedelta(days=i) for i in range(7)]
    days = [d for d in days if d != date(2026, 10, 16)]  # one missing day this year
    with httpx.Client(transport=httpx.MockTransport(_fake_portwatch(days))) as client:
        first = refresh_maritime(db, client, NOW)
        assert first.status == "succeeded" and first.rows_stored == 16 * 6 * 2
        assert refresh_maritime(db, client, NOW + timedelta(hours=1)) is None  # throttled
        assert refresh_maritime(db, client, NOW + timedelta(hours=7)).status == "succeeded"
    assert db.scalar(text("SELECT count(*) FROM maritime_aggregates")) == 16 * 6 * 2  # upserted, not duplicated
    assert db.scalar(text("SELECT count(*) FROM maritime_areas")) == 2

    overview = maritime_overview(db, NOW, None)
    bab = overview["chokepoints"][0]
    assert overview["latest_day"] == "2026-10-18" and bab["name"] == "Bab el-Mandeb Strait"
    assert bab["avg_7d"] == 20.0 and bab["avg_7d_last_year"] == 40.0 and bab["change_vs_last_year_pct"] == -50
    assert next(p for p in bab["series"] if p["day"] == "2026-10-16")["value"] is None  # missing stays empty
    assert len(bab["series"]) == 90 and bab["tankers_avg_7d"] == 5.0
    aden = overview["ports"][0]
    assert aden["avg_7d"] == 3.0 and aden["import_tonnes_7d"] == 30000 and aden["change_vs_last_year_pct"] == 0
    assert "International Monetary Fund, PortWatch" in overview["attribution"]
    assert maritime_overview(db, NOW, "SDN")["ports"] == []

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        assert client.get("/api/v1/maritime/overview?country=YEM").json()["ports"][0]["name"] == "Aden"
        assert client.get("/api/v1/maritime/overview?country=FRA").status_code == 404
    finally:
        app.dependency_overrides.clear()
