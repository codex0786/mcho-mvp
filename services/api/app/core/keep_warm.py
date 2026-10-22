"""Keep the free Render instance awake by requesting its own public URL.

Render's free web services sleep after 15 minutes without inbound traffic, and
waking takes about a minute (and occasionally fails). A request to the service's
public URL passes through Render's router, so it counts as traffic. One instance
running all month uses at most 744 of the 750 free instance hours, as long as no
other free service in the same Render workspace is also kept running.

Enabled only when a public HTTPS URL is known: Render sets RENDER_EXTERNAL_URL
automatically; KEEP_WARM_URL overrides it. KEEP_WARM_MINUTES=0 turns it off.
"""
import logging
import threading
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger("mcho.keep_warm")
PING_PATH = "/api/v1/health/live"


def ping_url(base_url: str) -> str | None:
    """The health URL to ping, or None if the base URL is not a plain HTTPS origin."""
    parts = urlsplit(base_url.strip())
    if parts.scheme != "https" or not parts.hostname or parts.query or parts.fragment:
        return None
    return f"https://{parts.netloc}{PING_PATH}"


def ping_once(client: httpx.Client, url: str) -> bool:
    try:
        response = client.get(url, timeout=httpx.Timeout(30.0, connect=10.0))
    except httpx.HTTPError as exc:
        logger.warning("keep_warm_ping_failed error_type=%s", type(exc).__name__)
        return False
    if response.status_code != 200:
        logger.warning("keep_warm_ping_failed status=%s", response.status_code)
        return False
    return True


def start(base_url: str, minutes: int) -> threading.Event | None:
    """Start a daemon thread pinging every ``minutes``; returns an Event that stops it."""
    url = ping_url(base_url) if base_url else None
    if url is None or minutes <= 0:
        if base_url:
            logger.warning("keep_warm_disabled reason=url_or_interval_invalid")
        return None
    stop = threading.Event()

    def run() -> None:
        with httpx.Client(follow_redirects=False, headers={"User-Agent": "MCHO keep-warm"}) as client:
            while not stop.wait(minutes * 60):
                ping_once(client, url)

    threading.Thread(target=run, name="keep-warm", daemon=True).start()
    logger.info("keep_warm_started interval_minutes=%s", minutes)
    return stop
