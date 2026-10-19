import logging

import pytest
from fastapi import HTTPException

from app.routers.health import ready


class FakeDatabase:
    def __init__(self, fail_on: str | None = None):
        self.fail_on = fail_on

    def execute(self, statement):
        sql = str(statement)
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("synthetic dependency failure")
        return None


def test_readiness_requires_database_postgis_and_redis(monkeypatch):
    monkeypatch.setattr("app.routers.health.redis_dependency_ready", lambda: True)
    result = ready(db=FakeDatabase())
    assert result["status"] == "ready"
    assert result["dependencies"] == {"database": "ok", "postgis": "ok", "redis": "ok"}


def test_readiness_fails_closed_if_redis_is_unavailable(monkeypatch):
    monkeypatch.setattr("app.routers.health.redis_dependency_ready", lambda: False)
    with pytest.raises(HTTPException) as exc:
        ready(db=FakeDatabase())
    assert exc.value.status_code == 503
    assert exc.value.detail["dependencies"]["redis"] == "unavailable"


def test_readiness_marks_postgis_unavailable_if_extension_probe_fails(monkeypatch):
    monkeypatch.setattr("app.routers.health.redis_dependency_ready", lambda: True)
    with pytest.raises(HTTPException) as exc:
        ready(db=FakeDatabase(fail_on="PostGIS_Full_Version"))
    assert exc.value.status_code == 503
    assert exc.value.detail["dependencies"]["database"] == "ok"
    assert exc.value.detail["dependencies"]["postgis"] == "unavailable"


def test_request_tracing_returns_correlation_id_and_does_not_log_bearer_token(caplog):
    from fastapi.testclient import TestClient
    from app.main import app

    token_marker = "DO_NOT_LOG_THIS_TEST_BEARER_TOKEN"
    caplog.set_level(logging.INFO, logger="mcho.request")
    client = TestClient(app)
    response = client.get("/", headers={
        "X-Request-ID": "test-trace-123",
        "Authorization": f"Bearer {token_marker}",
    })
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "test-trace-123"
    assert "request_finished" in caplog.text
    assert token_marker not in caplog.text


def test_redis_url_shape_never_includes_credentials():
    from app.routers.health import redis_url_shape

    shape = redis_url_shape("rediss://default:s3cr3t-pa55@fine-x-123.upstash.io:6379?ssl_cert_reqs=required")
    assert "s3cr3t" not in shape and "default" not in shape and "fine-x-123" not in shape
    assert shape == "scheme=rediss host_domain=upstash.io port=6379 has_password=True ssl_cert_reqs=required"


def test_redis_url_shape_flags_common_mistakes():
    from app.routers.health import redis_url_shape

    assert redis_url_shape("https://fine-x.upstash.io").startswith("scheme=https ")
    assert "ssl_cert_reqs=absent" in redis_url_shape("redis://default:pw@fine-x.upstash.io:6379")
    assert "has_password=False" in redis_url_shape("rediss://fine-x.upstash.io:6379")


def test_app_logging_reaches_a_handler_at_configured_level():
    import logging
    from app.main import configure_app_logging

    logger = configure_app_logging("warning")
    assert logger.handlers and logger.level == logging.WARNING
    configure_app_logging("info")
