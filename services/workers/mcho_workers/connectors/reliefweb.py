"""Read-only ReliefWeb API v2 connector.

Disabled unless a pre-approved appname and explicit country scope are configured.
It requests metadata only and never downloads report body content.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from .base import ConnectorStatus

API_URL = "https://api.reliefweb.int/v2/reports"


@dataclass(frozen=True)
class ReliefWebConfig:
    appname: str
    countries: tuple[str, ...]
    page_size: int = 100
    max_pages: int = 3
    initial_lookback_days: int = 7
    overlap_hours: int = 24

    @classmethod
    def from_env(cls) -> "ReliefWebConfig":
        countries = tuple(x.strip() for x in os.getenv("RELIEFWEB_COUNTRIES", "").split(",") if x.strip())

        def bounded_int(name: str, default: int, low: int, high: int) -> int:
            try:
                value = int(os.getenv(name, str(default)))
            except (TypeError, ValueError):
                value = default
            return max(low, min(value, high))

        return cls(
            appname=os.getenv("RELIEFWEB_APPNAME", "").strip(),
            countries=countries,
            page_size=bounded_int("RELIEFWEB_PAGE_SIZE", 100, 1, 100),
            max_pages=bounded_int("RELIEFWEB_MAX_PAGES", 3, 1, 10),
            initial_lookback_days=bounded_int("RELIEFWEB_INITIAL_LOOKBACK_DAYS", 7, 1, 30),
            overlap_hours=bounded_int("RELIEFWEB_OVERLAP_HOURS", 24, 1, 72),
        )


class ReliefWebConnector:
    def __init__(self, config: ReliefWebConfig | None = None, client: httpx.Client | None = None):
        self.config = config or ReliefWebConfig.from_env()
        self._client = client
        self._owns_client = client is None

    def status(self) -> ConnectorStatus:
        if not self.config.appname:
            return ConnectorStatus("reliefweb_reports", False, "Disabled: pre-approved RELIEFWEB_APPNAME is missing.")
        if not self.config.countries:
            return ConnectorStatus("reliefweb_reports", False, "Disabled: RELIEFWEB_COUNTRIES scope is empty.")
        return ConnectorStatus("reliefweb_reports", True, "Configured; database source approval is still required.")

    def _client_for_request(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(20.0, connect=5.0),
                headers={"User-Agent": "MCHO/0.1 (+https://github.com/codex0786/mcho-mvp)"},
                follow_redirects=False,
            )
        return self._client

    def fetch_page(self, start: datetime, end: datetime, offset: int) -> tuple[list[dict[str, Any]], int]:
        if not self.status().configured:
            raise RuntimeError("ReliefWeb connector is not configured.")
        body = {
            "filter": {
                "operator": "AND",
                "conditions": [
                    {"field": "country", "value": list(self.config.countries), "operator": "OR"},
                    {"field": "date.changed", "value": {"from": start.isoformat(), "to": end.isoformat()}},
                ],
            },
            "fields": {"include": [
                "title", "url", "date.created", "date.changed", "date.original", "source", "country",
                "primary_country", "language", "format",
            ]},
            "sort": ["date.changed:asc", "id:asc"],
            "limit": self.config.page_size,
            "offset": offset,
        }
        response = self._client_for_request().post(API_URL, params={"appname": self.config.appname}, json=body)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("ReliefWeb response did not contain a data list.")
        # ReliefWeb v2 has per-response count and whole-query totalCount.
        total_raw = payload.get("totalCount", len(payload["data"]))
        try:
            total = max(0, int(total_raw))
        except (TypeError, ValueError):
            total = len(payload["data"])
        return [row for row in payload["data"] if isinstance(row, dict)], total

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None
