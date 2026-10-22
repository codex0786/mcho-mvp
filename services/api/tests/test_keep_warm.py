import httpx

from app.core.keep_warm import ping_once, ping_url, start


def test_ping_url_accepts_only_plain_https_origins():
    assert ping_url("https://mcho-api.onrender.com") == "https://mcho-api.onrender.com/api/v1/health/live"
    assert ping_url("https://mcho-api.onrender.com/") == "https://mcho-api.onrender.com/api/v1/health/live"
    for bad in ("http://mcho-api.onrender.com", "https://x.test/?a=1", "not a url", ""):
        assert ping_url(bad) is None


def test_ping_once_reports_success_and_failure():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200 if len(calls) == 1 else 503)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert ping_once(client, "https://x.test/api/v1/health/live") is True
        assert ping_once(client, "https://x.test/api/v1/health/live") is False
    with httpx.Client(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")))) as client:
        assert ping_once(client, "https://x.test/api/v1/health/live") is False


def test_start_is_off_without_a_valid_url_or_interval():
    assert start("", 10) is None
    assert start("http://insecure.test", 10) is None
    assert start("https://x.test", 0) is None
    stop = start("https://x.test", 10)
    assert stop is not None
    stop.set()
