import io
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np
import pytest
import shapely
from sqlalchemy import text

from app.damage.analysis import damage_overview
from app.damage.unosat import (
    MAX_DOWNLOAD_BYTES, UnosatError, class_fields, damage_class, date_fields, download, eligible, pick_resource,
    read_damage_points, refresh_damage, srid_for,
)
from test_thermal import db  # noqa: F401 - shared PostGIS fixture (tests dir is on sys.path)

NOW = datetime(2026, 10, 22, 9, tzinfo=timezone.utc)


def _shapefile_zip(folder: Path, name: str, points: list[tuple[float, float]], fields: dict[str, list], crs: str) -> bytes:
    """A zipped shapefile written with GDAL, like the ones UNOSAT publishes."""
    import pyogrio.raw

    target = folder / name
    target.mkdir()
    pyogrio.raw.write(
        str(target / f"{name}.shp"), np.array(shapely.to_wkb(shapely.points(points)), dtype=object),
        [np.array(values, dtype=object) for values in fields.values()], list(fields), geometry_type="Point", crs=crs,
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for part in target.iterdir():
            archive.write(part, f"{name}/{part.name}")
    return buffer.getvalue()


def test_damage_classes_follow_unosat_codes_and_labels():
    assert [damage_class(v) for v in (1, "2", 3.0, 4, 11, 6, 7, None, float("nan"))] == [
        "destroyed", "severe", "moderate", "possible", "possible", None, None, None, None]
    assert damage_class("Possible Damage from adjacent impact, debris") == "possible"
    assert damage_class("Severe Damage") == "severe" and damage_class("No visible damage") is None


def test_field_detection_orders_numbered_columns():
    gdb = ["SiteID", "SensorDate", "Main_Damage_Site_Class", "SensorDate_2", "Main_Damage_Site_Class_2", "Main_Damage_Site_Class_10"]
    assert class_fields(gdb) == ["Main_Damage_Site_Class", "Main_Damage_Site_Class_2", "Main_Damage_Site_Class_10"]
    shp = ["SensorDate", "Main_Damag", "Main_Dam_1", "SensorDa_1", "Main_Dam_2", "Damage_Sta"]
    assert class_fields(shp) == ["Main_Dam_1", "Main_Dam_2"]
    assert date_fields(shp) == ["SensorDate", "SensorDa_1"]
    assert class_fields(["latitude", "Date"]) == [] and date_fields(["latitude", "Date"]) == ["Date"]


def test_srid_detection():
    assert srid_for("EPSG:4326") == 4326 and srid_for("EPSG:9707") == 4326 and srid_for("EPSG:32637") == 32637
    assert srid_for('COMPD_CS["WGS 84 + EGM96 height",GEOGCS["WGS 84",DATUM["WGS_1984"]]]') == 4326
    assert srid_for('PROJCS["Unknown",GEOGCS["WGS 84"]]') is None and srid_for(None) is None


def _package(pid, title, url, day, code="CE20231007PSE", group="pse", size=1000, fmt="Geodatabase"):
    return {"id": pid, "name": f"slug-{pid}", "title": title, "dataset_date": f"[{day}T00:00:00 TO {day}T23:59:59]",
            "notes": f"**UNOSAT code: {code}** This map illustrates damage.", "caveats": "Preliminary.",
            "license_title": "Creative Commons Attribution Share-Alike (CC BY-SA)", "license_url": "https://example.test/by-sa",
            "groups": [{"name": group}], "resources": [{"url": url, "format": fmt, "size": size}] if url else []}


def test_catalogue_filters_and_resource_choice():
    assert eligible(_package("a", "UNOSAT Gaza Strip Comprehensive Damage Assessment", None, "2025-10-31"))
    assert not eligible(_package("b", "Gaza Strip Cropland Damage Assessment", None, "2025-10-31"))
    assert not eligible(_package("c", "Satellite detected water extent", None, "2025-10-31"))
    assert not eligible(_package("d", "Damaged structures in Sarpol-e-Zahab", None, "2017-11-20", code="EQ20171112IRQ"))
    package = _package("e", "Damage", "https://unosat.org/a_shp.zip", "2025-01-01", fmt="SHP")
    package["resources"].append({"url": "https://unosat.org/a_gdb.zip", "format": "Geodatabase", "size": 10})
    assert pick_resource(package) == "https://unosat.org/a_gdb.zip"
    assert pick_resource(_package("f", "Damage", "https://evil.test/x.zip", "2025-01-01")) is None
    assert pick_resource(_package("g", "Damage", "https://unosat.org/x.zip", "2025-01-01", size=MAX_DOWNLOAD_BYTES + 1)) is None


def test_reader_uses_latest_class_and_reprojects(tmp_path):
    # Three structures in UTM 37N near Daraa; the second was re-assessed as no visible damage (6).
    data = _shapefile_zip(tmp_path, "Daraa_Damage_Points", [(227947.9, 3612061.1), (228000.0, 3612100.0), (228100.0, 3612150.0)],
                          {"SensorDate": ["2013-09-07", "2013-09-07", None], "Main_Dam_1": ["3", "1", None],
                           "SensorDa_1": ["2017-02-07", "2017-02-07", "2017-02-07"], "Main_Dam_2": ["1", "6", "2"]}, "EPSG:32637")
    archive = tmp_path / "a.zip"
    archive.write_bytes(data)
    points = read_damage_points(archive)
    assert points["srid"] == 32637 and points["imagery_date"] == date(2017, 2, 7)
    assert points["class"] == ["destroyed", "severe"] and len(points["x"]) == 2


def test_reader_counts_unclassified_damage_layers_and_rejects_others(tmp_path):
    data = _shapefile_zip(tmp_path, "ElFasher_DA_20240731", [(25.36, 13.61), (25.38, 13.62)],
                          {"Date": ["2024-05-18", "2024-07-31"]}, "EPSG:4326")
    (tmp_path / "a.zip").write_bytes(data)
    points = read_damage_points(tmp_path / "a.zip")
    assert points["class"] == ["unclassified", "unclassified"] and points["imagery_date"] == date(2024, 7, 31)
    other = _shapefile_zip(tmp_path, "Population_Density", [(25.36, 13.61)], {"Date": ["2024-05-18"]}, "EPSG:4326")
    (tmp_path / "b.zip").write_bytes(other)
    with pytest.raises(UnosatError):
        read_damage_points(tmp_path / "b.zip")


def test_download_refuses_other_hosts_and_large_files(tmp_path):
    big = httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * (MAX_DOWNLOAD_BYTES + 10)))
    with httpx.Client(transport=big) as client:
        with pytest.raises(UnosatError, match="larger"):
            download(client, "https://unosat.org/big.zip", tmp_path / "f.zip")
        with pytest.raises(UnosatError, match="host"):
            download(client, "https://example.test/f.zip", tmp_path / "f.zip")
    redirect = httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": "https://evil.test/f.zip"}))
    with httpx.Client(transport=redirect) as client:
        with pytest.raises(UnosatError, match="host"):
            download(client, "https://cern.ch/unosat-maps/f.zip", tmp_path / "f.zip")


def test_refresh_maps_assessments_and_hides_superseded_ones(db, tmp_path):  # noqa: F811
    for table in ("damage_cells", "damage_assessments", "damage_refreshes"):
        db.execute(text(f"DELETE FROM {table}"))
    # Older assessment of north Gaza, then a newer one covering the whole area.
    older = _shapefile_zip(tmp_path, "Damage_Sites_North", [(34.50, 31.53), (34.501, 31.531), (34.51, 31.54)],
                           {"SensorDate": ["2024-01-06"] * 3, "Main_Damage_Site_Class": [1, 2, 6]}, "EPSG:4326")
    newer = _shapefile_zip(tmp_path, "Damage_Sites_Strip", [(34.50, 31.53), (34.501, 31.531), (34.51, 31.54), (34.30, 31.30)],
                           {"SensorDate": ["2025-10-11"] * 4, "Main_Damage_Site_Class": [1, 1, 3, 4]}, "EPSG:4326")
    files = {"https://unosat.org/north.zip": older, "https://unosat.org/strip.zip": newer, "https://unosat.org/broken.zip": b"not a zip"}
    catalogue = [
        _package("p-strip", "Gaza Strip Comprehensive Damage Assessment - 11 October 2025", "https://unosat.org/strip.zip", "2025-10-31"),
        _package("p-north", "North Gaza Damage Assessment - January 2024", "https://unosat.org/north.zip", "2024-01-20"),
        _package("p-north-copy", "North Gaza Damage Assessment (same file)", "https://unosat.org/north.zip", "2024-01-10"),
        _package("p-nofile", "Damage Assessment of Idlib", None, "2014-11-07", code="CE20130604SYR", group="syr"),
        _package("p-broken", "Damage Assessment of Benghazi", "https://unosat.org/broken.zip", "2016-08-12", code="CE20150814LBY", group="lby"),
        _package("p-flood", "Satellite detected water extent", "https://unosat.org/flood.zip", "2025-01-03", code="FL20250101SDN", group="sdn"),
    ]

    def handler(request):
        url = str(request.url)
        if url.startswith("https://data.humdata.org/api/3/action/package_search"):
            return httpx.Response(200, json={"result": {"count": len(catalogue), "results": catalogue}})
        return httpx.Response(200, content=files[url]) if url in files else httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = refresh_damage(db, client, NOW)
        assert first.status == "succeeded" and first.rows_stored == 2
        assert refresh_damage(db, client, NOW + timedelta(hours=1)) is None  # throttled, nothing pending
    status = dict(db.execute(text("SELECT id, status FROM damage_assessments")).all())
    assert status == {"p-strip": "mapped", "p-north": "mapped", "p-north-copy": "catalogue", "p-nofile": "catalogue", "p-broken": "failed"}

    overview = damage_overview(db, NOW)
    by_id = {a["id"]: a for a in overview["assessments"]}
    assert by_id["p-strip"]["on_map"] and by_id["p-strip"]["counts"] == {"destroyed": 2, "severe": 0, "moderate": 1, "possible": 1, "unclassified": 0}
    assert by_id["p-strip"]["imagery_date"] == "2025-10-11"
    assert not by_id["p-north"]["on_map"] and by_id["p-north"]["superseded_by"].startswith("Gaza Strip")
    assert by_id["p-north"]["counts"]["destroyed"] == 1 and by_id["p-north"]["counts"]["severe"] == 1  # class 6 is not damage
    assert overview["totals_on_map"]["destroyed"] == 2  # superseded structures are not counted twice
    assert sum(f["properties"]["total"] for f in overview["cells"]["features"]) == 4
    assert {f["properties"]["assessment"] for f in overview["cells"]["features"]} == {by_id["p-strip"]["title"]}
    assert "Same data file" in by_id["p-north-copy"]["status_detail"] and by_id["p-broken"]["status_detail"]
    assert [a["id"] for a in damage_overview(db, NOW, "SYR")["assessments"]] == ["p-nofile"]
