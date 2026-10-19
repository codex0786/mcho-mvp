import httpx
import pytest

from mcho_workers.celery_app import ingest_source
from mcho_workers.ingestion import TransientProviderError, is_transient_provider_error


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://api.reliefweb.int/v2/reports")
    return httpx.HTTPStatusError("provider error", request=request, response=httpx.Response(code, request=request))


@pytest.mark.parametrize("code", [408, 429, 500, 502, 503, 504])
def test_rate_limits_and_server_errors_are_retried(code):
    assert is_transient_provider_error(_status_error(code))


@pytest.mark.parametrize("code", [400, 401, 403, 404, 410, 422])
def test_client_errors_are_not_retried(code):
    assert not is_transient_provider_error(_status_error(code))


def test_transport_failures_are_retried():
    request = httpx.Request("GET", "https://api.reliefweb.int/v2/reports")
    assert is_transient_provider_error(httpx.ConnectTimeout("timed out", request=request))
    assert is_transient_provider_error(httpx.ConnectError("refused", request=request))
    assert is_transient_provider_error(httpx.RemoteProtocolError("closed", request=request))
    assert not is_transient_provider_error(httpx.UnsupportedProtocol("ftp", request=request))


def test_celery_only_auto_retries_transient_provider_errors():
    assert ingest_source.autoretry_for == (TransientProviderError,)
