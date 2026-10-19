"""Provider payload normalization, deliberately separated from database/worker imports."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _names(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        name = value.get("name")
        return [name.strip()] if isinstance(name, str) and name.strip() else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_names(item))
        return result
    return []


def normalize_reliefweb_record(row: dict[str, Any], retrieved_at: datetime) -> dict[str, Any]:
    """Normalize provider report metadata while preserving the source link and provenance.

    MCHO never fetches or persists the original article body using this adapter.
    """
    external_id = str(row.get("id", "")).strip()
    fields = row.get("fields")
    if not external_id or not isinstance(fields, dict):
        raise ValueError("Report record is missing its provider id or fields object.")

    title = fields.get("title")
    if not isinstance(title, str) or not title.strip():
        title = f"Untitled ReliefWeb report {external_id}"
    canonical_url = fields.get("url")
    if not isinstance(canonical_url, str) or not canonical_url.startswith("https://reliefweb.int/"):
        raise ValueError("Report has no valid canonical ReliefWeb URL; record withheld.")

    dates = fields.get("date") if isinstance(fields.get("date"), dict) else {}
    created_at = _parse_datetime(dates.get("created"))
    changed_at = _parse_datetime(dates.get("changed")) or created_at
    published_at = _parse_datetime(dates.get("original")) or created_at
    metadata = {
        "provider": "reliefweb",
        "external_id": external_id,
        "title": title.strip(),
        "url": canonical_url,
        "provider_created_at": created_at.isoformat() if created_at else None,
        "provider_changed_at": changed_at.isoformat() if changed_at else None,
        "published_at": published_at.isoformat() if published_at else None,
        "countries": sorted(set(_names(fields.get("country")))),
        "primary_countries": sorted(set(_names(fields.get("primary_country")))),
        "sources": sorted(set(_names(fields.get("source")))),
        "languages": sorted(set(_names(fields.get("language")))),
        "formats": sorted(set(_names(fields.get("format")))),
        "retrieved_at": retrieved_at.astimezone(timezone.utc).isoformat(),
        "content_policy": "metadata_and_link_only; original report content remains at provider",
    }
    stable_payload = {key: value for key, value in metadata.items() if key != "retrieved_at"}
    content_hash = hashlib.sha256(
        json.dumps(stable_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "external_id": external_id,
        "title": metadata["title"],
        "canonical_url": canonical_url,
        "published_at": published_at,
        "content_hash": content_hash,
        "metadata": metadata,
    }
