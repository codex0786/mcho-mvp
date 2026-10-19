import json
from datetime import datetime, timezone

import httpx
import pytest

from mcho_workers.connectors.reliefweb import ReliefWebConfig, ReliefWebConnector
from mcho_workers.normalization import normalize_reliefweb_record


def sample_row(report_id="12345", title="Situation update"):
    return {
        "id": report_id,
        "fields": {
            "title": title,
            "url": f"https://reliefweb.int/report/sample/{report_id}",
            "date": {
                "created": "2026-10-18T12:00:00+00:00",
                "original": "2026-10-17T08:30:00+00:00",
            },
            "country": [{"name": "Lebanon"}],
            "primary_country": [{"name": "Lebanon"}],
            "source": [{"name": "Example Source"}],
            "language": [{"name": "English"}],
            "format": [{"name": "Situation Report"}],
        },
    }


def test_connector_fails_closed_without_preapproved_appname_and_scope():
    missing_appname = ReliefWebConnector(ReliefWebConfig(appname="", countries=("Lebanon",)))
    assert not missing_appname.status().configured
    with pytest.raises(RuntimeError):
        missing_appname.fetch_page(datetime.now(timezone.utc), datetime.now(timezone.utc), 0)

    missing_scope = ReliefWebConnector(ReliefWebConfig(appname="approved-appname", countries=()))
    assert not missing_scope.status().configured


def test_reliefweb_fetch_uses_total_count_and_requests_metadata_only():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"count": 1, "totalCount": 251, "data": [sample_row()]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    connector = ReliefWebConnector(
        ReliefWebConfig(appname="approved-mcho-app", countries=("Lebanon", "Syria"), page_size=50),
        client=client,
    )
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 19, tzinfo=timezone.utc)
    rows, total = connector.fetch_page(start, end, 50)
    assert total == 251
    assert len(rows) == 1
    assert "appname=approved-mcho-app" in seen["url"]
    assert seen["body"]["offset"] == 50
    assert seen["body"]["limit"] == 50
    assert "body" not in seen["body"]["fields"]["include"]
    connector.close()
    client.close()


def test_connector_environment_limits_are_bounded_and_invalid_values_fall_back(monkeypatch):
    monkeypatch.setenv("RELIEFWEB_APPNAME", "approved-mcho-app")
    monkeypatch.setenv("RELIEFWEB_COUNTRIES", "Lebanon, Syria")
    monkeypatch.setenv("RELIEFWEB_PAGE_SIZE", "9999")
    monkeypatch.setenv("RELIEFWEB_MAX_PAGES", "not-a-number")
    config = ReliefWebConfig.from_env()
    assert config.countries == ("Lebanon", "Syria")
    assert config.page_size == 100
    assert config.max_pages == 3


def test_metadata_normalization_preserves_provenance_and_never_stores_body():
    now = datetime(2026, 10, 19, 3, 0, tzinfo=timezone.utc)
    row = sample_row()
    row["fields"]["body"] = "This article body must never be copied into MCHO."
    normalized = normalize_reliefweb_record(row, now)
    assert normalized["external_id"] == "12345"
    assert normalized["canonical_url"].startswith("https://reliefweb.int/")
    assert normalized["metadata"]["countries"] == ["Lebanon"]
    assert normalized["metadata"]["provider_created_at"].startswith("2026-10-18T12:00:00")
    assert "body" not in normalized["metadata"]
    assert "This article body" not in json.dumps(normalized, default=str)


def test_metadata_normalization_rejects_noncanonical_external_urls():
    row = sample_row()
    row["fields"]["url"] = "https://example.com/copied-report"
    with pytest.raises(ValueError, match="canonical ReliefWeb URL"):
        normalize_reliefweb_record(row, datetime.now(timezone.utc))


def test_content_hash_stays_stable_when_retrieved_at_changes():
    row = sample_row()
    first = normalize_reliefweb_record(row, datetime(2026, 10, 19, 3, 0, tzinfo=timezone.utc))
    second = normalize_reliefweb_record(row, datetime(2026, 10, 19, 4, 0, tzinfo=timezone.utc))
    assert first["content_hash"] == second["content_hash"]
