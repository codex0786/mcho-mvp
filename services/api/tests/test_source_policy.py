from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.source_policy import source_is_publishable


def _source(**overrides):
    fields = dict(
        active=True,
        license_status="approved",
        terms_reviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        terms_reviewed_by="https://issuer.example.test/|admin-1",
        license_terms_url="https://example.org/terms",
        retention_policy="Store metadata and canonical links only.",
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_fully_reviewed_active_source_is_publishable():
    assert source_is_publishable(_source())


@pytest.mark.parametrize("override", [
    {"active": False},
    {"license_status": "unreviewed"},
    {"license_status": "synthetic"},
    {"terms_reviewed_at": None},
    {"terms_reviewed_by": None},
    {"terms_reviewed_by": ""},
    {"license_terms_url": None},
    {"retention_policy": None},
    {"retention_policy": ""},
])
def test_any_missing_governance_field_blocks_publication(override):
    assert not source_is_publishable(_source(**override))


def test_missing_source_is_not_publishable():
    assert not source_is_publishable(None)
