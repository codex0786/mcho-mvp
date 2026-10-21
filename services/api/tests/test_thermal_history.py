from datetime import date, datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.thermal.history import compact_points, last_year, parse_availability, plan_requests, refresh_history
from test_thermal import HEADER, KEY, _add, db  # noqa: F401 - shared PostGIS fixture (tests dir is on sys.path)

FAMILIES = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"]
AVAILABILITY = (
    "data_id,min_date,max_date\n"
    "VIIRS_SNPP_SP,2012-01-20,2026-06-30\nVIIRS_NOAA20_SP,2018-04-01,2026-06-30\n"
    "VIIRS_NOAA21_NRT,2024-01-17,2026-10-21\nVIIRS_SNPP_NRT,2026-07-01,2026-10-21\n"
)


def test_availability_is_parsed_defensively():
    ranges = parse_availability(AVAILABILITY + "garbage,row\nMODIS_NRT,2000-01-01,2026-10-21\n")
    assert ranges["VIIRS_SNPP_SP"] == (date(2012, 1, 20), date(2026, 6, 30))
    assert "MODIS_NRT" not in ranges and parse_availability("Invalid MAP_KEY.") == {}


def test_plan_chunks_missing_days_by_best_source_and_resumes():
    ranges = parse_availability(AVAILABILITY)
    plan = plan_requests(set(), ranges, FAMILIES, date(2026, 10, 21))
    assert len(plan) == 15 and all(day_range == 5 for *_, day_range in plan)
    assert {(family, source) for family, source, _, _ in plan} == {
        ("VIIRS_SNPP_NRT", "VIIRS_SNPP_SP"), ("VIIRS_NOAA20_NRT", "VIIRS_NOAA20_SP"), ("VIIRS_NOAA21_NRT", "VIIRS_NOAA21_NRT"),
    }
    fetched = {("VIIRS_SNPP_NRT", date(2025, 9, 29) + timedelta(days=i)) for i in range(25)}
    assert all(family != "VIIRS_SNPP_NRT" for family, *_ in plan_requests(fetched, ranges, FAMILIES, date(2026, 10, 21)))
    # A satellite with no archive for last year is simply not planned.
    no_noaa21 = {k: v for k, v in ranges.items() if k != "VIIRS_NOAA21_NRT"}
    assert all(family != "VIIRS_NOAA21_NRT" for family, *_ in plan_requests(set(), no_noaa21, FAMILIES, date(2026, 10, 21)))


def test_last_year_and_compaction():
    assert last_year(date(2026, 10, 21)) == date(2025, 10, 21)
    assert last_year(date(2028, 2, 29)) == date(2027, 2, 28)
    rows = [{"acquired_at": "2025-10-20T01:00:00+00:00", "latitude": 15.551, "longitude": 32.531},
            {"acquired_at": "2025-10-20T13:00:00+00:00", "latitude": 15.549, "longitude": 32.529},
            {"acquired_at": "2025-10-21T01:00:00+00:00", "latitude": 15.551, "longitude": 32.531}]
    assert sorted((p["day"], p["n"]) for p in compact_points(rows)) == [("2025-10-20", 2), ("2025-10-21", 1)]


def test_history_refresh_and_year_on_year_comparison(db, monkeypatch):  # noqa: F811
    from app.thermal.analysis import comparable_daily, country_trend, insights

    monkeypatch.setattr(settings, "nasa_firms_api_key", KEY)
    monkeypatch.setattr(settings, "firms_products", "VIIRS_SNPP_NRT")
    now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
    # Last year: 3 Sudan detections per day on 2025-10-14..20 (Suomi NPP archive), plus one offshore.
    lines = [HEADER]
    for offset in range(7):
        day = (date(2025, 10, 14) + timedelta(days=offset)).isoformat()
        lines += [f"{15.5 + i * 0.1},32.5,330,0.4,0.4,{day},0130,N,VIIRS,n,2.0,290,5,N" for i in range(3)]
    lines.append("26.5,52.0,330,0.4,0.4,2025-10-15,0130,N,VIIRS,n,2.0,290,5,N")
    archive = "\n".join(lines) + "\n"
    requests = []

    def handler(request):
        path = request.url.path.replace(KEY, "KEY")
        requests.append(path)
        if "/data_availability/" in path:
            return httpx.Response(200, text=AVAILABILITY)
        return httpx.Response(200, text=archive if "/2025-10-14" in path or "/2025-10-19" in path else HEADER + "\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        summary = refresh_history(db, client, now)
    assert summary["status"] == "succeeded" and summary["requests"] == 5 and summary["remaining"] == 0
    assert all("VIIRS_SNPP_SP" in path for path in requests[1:])
    fetched_days = db.execute(__import__("sqlalchemy").text("SELECT count(*) FROM thermal_history_fetches")).scalar()
    assert fetched_days == 25  # every planned day is recorded, including days with no detections

    # This year: 2 Sudan detections per day on 2026-10-14..20.
    for offset in range(7):
        for i in range(2):
            _add(db, 15.5 + i * 0.1, 32.5, datetime(2026, 10, 14 + offset, 1, tzinfo=timezone.utc), "SDN")
    db.commit()

    pairs = comparable_daily(db, [date(2026, 10, 20), date(2026, 10, 10), date(2026, 9, 20)], "SDN")
    assert pairs[("SDN", date(2026, 10, 20))] == {"this_year": 2, "last_year": 3}
    assert pairs[("SDN", date(2026, 10, 10))]["last_year"] == 0  # fetched with no detections: a real zero
    assert ("SDN", date(2026, 9, 20)) not in pairs  # last year's day was never fetched: no comparison

    # 2026-10-14 is the first, partial day of this year's data, so it is not compared.
    trend = country_trend(db, now, "SDN", 21)
    assert trend["year_on_year_7d"] == {"days": 6, "this_year": 12, "last_year": 18, "ratio": 0.67}
    point = next(p for p in trend["series"] if p["date"] == "2026-10-20")
    assert point["last_year_total"] == 3 and point["comparable_total"] == 2
    sudan = next(c for c in insights(db, now)["countries"] if c["iso_a3"] == "SDN")
    assert sudan["year_on_year_7d"] == {"days": 6, "this_year": 12, "last_year": 18, "ratio": 0.67}

    # A second run has nothing left to fetch.
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert refresh_history(db, client, now)["requests"] == 0
