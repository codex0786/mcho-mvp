import csv
import io
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import text

from app.conflict import heat_match
from app.conflict.analysis import conflict_overview
from app.conflict.heat_match import assess, group_area, group_events, plan_chunks
from app.conflict.ucdp import UcdpError, fetch_release, parse_events, recent_releases, refresh_ucdp
from app.core.config import settings
from test_thermal import HEADER, db  # noqa: F401 - shared PostGIS fixture (tests dir is on sys.path)

NOW = datetime(2026, 10, 22, 9, tzinfo=timezone.utc)
COLUMNS = ["id", "relid", "year", "active_year", "code_status", "type_of_violence", "conflict_new_id", "conflict_name", "dyad_new_id",
           "dyad_name", "side_a", "side_b", "number_of_sources", "where_prec", "where_description", "adm_1", "latitude", "longitude",
           "country", "region", "event_clarity", "date_prec", "date_start", "date_end", "deaths_a", "deaths_b", "deaths_civilians",
           "deaths_unknown", "best", "high", "low"]


def ucdp_csv(*events: dict) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS)
    writer.writeheader()
    for event in events:
        row = {column: "" for column in COLUMNS}
        row.update({"relid": f"R-{event['id']}", "code_status": "Clear", "type_of_violence": 1, "conflict_name": "Sudan: Government",
                    "dyad_name": "Government of Sudan - RSF", "side_a": "Government of Sudan", "side_b": "RSF", "where_prec": 1,
                    "date_prec": 1, "event_clarity": 1, "deaths_civilians": 0, "best": 10, "low": 8, "high": 12, "region": "Africa",
                    "number_of_sources": 2})
        row.update(event)
        writer.writerow(row)
    return "﻿" + out.getvalue()


def event(**values) -> dict:
    base = {"id": 1, "latitude": 13.6, "longitude": 25.35, "date_start": date(2026, 9, 10), "date_end": date(2026, 9, 10), "where_prec": 1}
    return {**base, **values}


def test_recent_releases_walk_back_across_years():
    assert recent_releases(date(2026, 2, 3), 3) == ["26.0.2", "26.0.1", "25.0.12", "25.0.11"]


def test_parse_events_keeps_valid_rows_in_the_region():
    body = ucdp_csv(
        {"id": 1, "latitude": 13.6, "longitude": 25.35, "country": "Sudan", "date_start": "2026-09-10 00:00:00.000", "date_end": "2026-09-10 00:00:00.000"},
        {"id": 2, "latitude": 19.4, "longitude": -99.1, "country": "Mexico", "date_start": "2026-09-10", "date_end": "2026-09-10"},
        {"id": 3, "latitude": "", "longitude": 25.0, "country": "Sudan", "date_start": "2026-09-10", "date_end": "2026-09-10"},
        {"id": 4, "latitude": 13.6, "longitude": 25.35, "country": "Sudan", "date_start": "2026-09-12", "date_end": "2026-09-10"},
        {"id": 5, "latitude": 13.6, "longitude": 25.35, "country": "Sudan", "date_start": "2026-09-10", "date_end": "2026-09-10", "type_of_violence": 9},
    )
    rows, total = parse_events(body, "26.0.9")
    assert total == 5 and [r["id"] for r in rows] == [1]
    assert rows[0]["date_start"] == "2026-09-10" and rows[0]["deaths_best"] == 10 and rows[0]["release"] == "26.0.9"


def test_fetch_release_handles_unpublished_unchanged_and_bad_files():
    for response in (httpx.Response(404), httpx.Response(304)):
        with httpx.Client(transport=httpx.MockTransport(lambda r, resp=response: resp)) as client:
            assert fetch_release(client, "26.0.10", None)[0] is None
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>maintenance</html>"))) as client:
        with pytest.raises(UcdpError):
            fetch_release(client, "26.0.9", None)


def test_grouping_and_request_area():
    events = [event(id=1), event(id=2, latitude=13.9, longitude=25.8), event(id=3, date_start=date(2026, 9, 25), date_end=date(2026, 9, 25)),
              event(id=4, latitude=15.6, longitude=32.5, where_prec=2)]
    groups = group_events(events)
    assert sorted(len(g) for g in groups) == [1, 1, 2]
    west, south, east, north = map(float, group_area([events[3]]).split(","))
    assert round(north - south, 2) == round(2 * 25 / 111, 2) and east - west > north - south  # wider in longitude away from the equator


def test_plan_chunks_prefers_the_archive_and_waits_for_missing_days():
    ranges = {"VIIRS_NOAA20_SP": (date(2018, 1, 1), date(2026, 9, 5)), "VIIRS_NOAA20_NRT": (date(2026, 7, 1), date(2026, 10, 21))}
    chunks = plan_chunks(date(2026, 9, 2), date(2026, 9, 11), "VIIRS_NOAA20_NRT", ranges)
    assert chunks == [("VIIRS_NOAA20_SP", date(2026, 9, 2), 4), ("VIIRS_NOAA20_NRT", date(2026, 9, 6), 5), ("VIIRS_NOAA20_NRT", date(2026, 9, 11), 1)]
    assert plan_chunks(date(2026, 10, 20), date(2026, 10, 23), "VIIRS_NOAA20_NRT", ranges) is None


def test_assess_separates_persistent_sites_and_respects_radius_and_window():
    e = event()
    flare = {"latitude": 13.61, "longitude": 25.36}
    detections = [{"day": date(2026, 9, 1) + timedelta(days=i), **flare, "frp": 3.0} for i in range(5)]  # 5 baseline days
    detections += [
        {"day": date(2026, 9, 10), **flare, "frp": 4.0},  # persistent site on the day: excluded
        {"day": date(2026, 9, 11), "latitude": 13.62, "longitude": 25.33, "frp": 25.0},  # ~3 km, day after: matched
        {"day": date(2026, 9, 10), "latitude": 13.6, "longitude": 25.45, "frp": 90.0},  # ~11 km: outside 5 km
        {"day": date(2026, 9, 13), "latitude": 13.6, "longitude": 25.35, "frp": 50.0},  # outside the window
    ]
    result = assess(e, detections)
    assert result["heat_status"] == "heat" and result["heat_detections"] == 1 and result["heat_persistent_excluded"] == 1
    assert result["heat_max_frp"] == 25.0 and 2 < result["heat_nearest_km"] < 4 and result["heat_radius_km"] == 5.0
    assert assess(e, detections[:6])["heat_status"] == "persistent_only"
    assert assess(e, [])["heat_status"] == "no_heat"
    assert assess(event(where_prec=2), detections)["heat_detections"] == 2  # 25 km radius includes the 11 km detection


def test_refresh_stores_mena_events_and_cross_checks_heat(db, monkeypatch):  # noqa: F811
    for table in ("ucdp_events", "ucdp_releases", "ucdp_refreshes", "thermal_detections"):
        db.execute(text(f"DELETE FROM {table}"))
    monkeypatch.setattr(settings, "nasa_firms_api_key", "a" * 32)
    september = ucdp_csv(
        {"id": 101, "latitude": 13.6, "longitude": 25.35, "country": "Sudan", "date_start": "2026-09-10", "date_end": "2026-09-10", "best": 30, "low": 25, "high": 40, "deaths_civilians": 12},
        {"id": 102, "latitude": 14.8, "longitude": 42.7, "country": "Yemen (North Yemen)", "date_start": "2026-09-12", "date_end": "2026-09-12", "best": 3, "type_of_violence": 1,
         "dyad_name": "Government of Yemen - Ansarallah", "where_prec": 1},  # just off the Red Sea coast
        {"id": 103, "latitude": 15.5, "longitude": 32.5, "country": "Sudan", "date_start": "2026-09-01", "date_end": "2026-09-30", "date_prec": 4, "best": 7},
        {"id": 104, "latitude": 15.0, "longitude": 60.0, "country": "Yemen (North Yemen)", "date_start": "2026-09-05", "date_end": "2026-09-05", "best": 1},
        {"id": 105, "latitude": 13.5, "longitude": 22.0, "country": "Chad", "date_start": "2026-09-05", "date_end": "2026-09-05", "best": 4},
    )
    august = ucdp_csv({"id": 90, "latitude": 13.0, "longitude": 25.0, "country": "Sudan", "date_start": "2026-08-20", "date_end": "2026-08-20", "best": 5, "where_prec": 3})
    firms_rows = ["13.62,25.33,330,0.4,0.4,2026-09-11,0130,N20,VIIRS,n,2.0NRT,290,25.0,N"]
    requests = []

    def handler(request):
        url = str(request.url)
        requests.append(url)
        if "GEDEvent_v26_0_9.csv" in url:
            return httpx.Response(200, text=september, headers={"etag": '"sep-1"'})
        if "GEDEvent_v26_0_8.csv" in url:
            return httpx.Response(200, text=august)
        if "ucdp.uu.se" in url:
            return httpx.Response(404)
        if "data_availability" in url:
            return httpx.Response(200, text="data_id,min_date,max_date\nVIIRS_NOAA20_NRT,2026-06-01,2026-10-21\nVIIRS_SNPP_NRT,2026-06-01,2026-10-21\n")
        if "/api/area/csv/" in url:
            return httpx.Response(200, text=HEADER + "\n" + ("\n".join(firms_rows) if "VIIRS_NOAA20" in url and "25.30" in url and url.endswith("/2026-09-07") else "") + "\n")
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = refresh_ucdp(db, client, now=NOW)
        assert first.status == "succeeded" and first.rows_stored == 4 and first.heat_checked == 2
        assert refresh_ucdp(db, client, now=NOW + timedelta(hours=1)) is None  # throttled; nothing pending
        etag_sent = [r for r in requests if "GEDEvent_v26_0_9" in r]
    assert len(etag_sent) == 1
    stored = dict(db.execute(text("SELECT id, country_code FROM ucdp_events")).all())
    assert stored == {101: "SDN", 102: "YEM", 103: "SDN", 90: "SDN"}  # open sea and Chad (near the border) dropped; coast assigned to Yemen
    status = dict(db.execute(text("SELECT id, heat_status FROM ucdp_events")).all())
    assert status == {101: "heat", 102: "no_heat", 103: "not_checkable", 90: "not_checkable"}

    overview = conflict_overview(db, NOW)
    assert overview["period"]["months"] == ["2026-07", "2026-08", "2026-09"] and overview["period"]["missing_months"] == ["2026-07"]
    assert overview["by_month"][0] == {"month": "2026-07", "fetched": False, "events": None, "deaths_best": None}
    assert overview["totals"] == {"events": 4, "deaths_best": 45, "deaths_low": 49, "deaths_high": 76, "deaths_civilians": 12}
    sudan = overview["by_country"][0]
    assert sudan["country_code"] == "SDN" and sudan["deaths_best"] == 42 and sudan["by_type"]["State-based conflict"] == 42
    assert overview["heat_check"]["checked"] == 2 and overview["heat_check"]["with_heat"] == 1 and overview["heat_check"]["share_with_heat"] == 0.5
    top = overview["events_with_heat"][0]
    assert top["id"] == 101 and top["heat"]["detections"] == 1 and top["deaths_civilians"] == 12
    assert len(overview["events"]["features"]) == 4
    assert [c["country_code"] for c in conflict_overview(db, NOW, "YEM")["by_country"]] == ["YEM"]


def test_heat_checks_wait_without_a_firms_key(db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "nasa_firms_api_key", "")
    assert heat_match.check_pending_events(db, httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))), NOW) == 0
