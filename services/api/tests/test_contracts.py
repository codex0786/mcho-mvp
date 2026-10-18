from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import Settings, settings
from app.core.review_policy import apply_review_decision
from app.core.security import require_reviewer
from app.schemas.events import CorrectionIn, EventOut, ReviewDecisionIn


def test_review_decision_accepts_only_known_values():
    valid = ReviewDecisionIn(decision="verify", rationale="Compared two independent source records.")
    assert valid.decision == "verify"
    with pytest.raises(ValidationError):
        ReviewDecisionIn(decision="publish_anything", rationale="This should not be accepted")
    with pytest.raises(ValidationError):
        ReviewDecisionIn(decision="verify", rationale="short")


def test_correction_rejects_invalid_verification_status():
    with pytest.raises(ValidationError):
        CorrectionIn(rationale="Correcting the event after source review.", verification_status="trusted")


def test_event_out_schema_contract():
    now = datetime.now(timezone.utc)
    item = EventOut(
        id=uuid4(), event_type="infrastructure_damage", summary="Fixture only", event_start=now,
        event_end=None, country_code="LB", status="published", verification_status="verified",
        attribution_status="unknown", confidence_label="moderate", spatial_uncertainty_m=100,
        is_synthetic=False, created_at=now, updated_at=now,
    )
    assert item.country_code == "LB"
    assert item.attribution_status == "unknown"


def test_reviewer_authentication_fails_closed_when_no_key(monkeypatch):
    monkeypatch.setattr(settings, "reviewer_api_key", "")
    with pytest.raises(HTTPException) as exc:
        require_reviewer(x_reviewer_key=None)
    assert exc.value.status_code == 503


def test_reviewer_authentication_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(settings, "reviewer_api_key", "unit-test-only-secret")
    with pytest.raises(HTTPException) as exc:
        require_reviewer(x_reviewer_key="incorrect")
    assert exc.value.status_code == 403


def test_reviewer_authentication_accepts_matching_key(monkeypatch):
    monkeypatch.setattr(settings, "reviewer_api_key", "unit-test-only-secret")
    assert require_reviewer(x_reviewer_key="unit-test-only-secret") == "api-key-reviewer"


def test_database_url_encodes_special_characters():
    password = "p@ss:/word#?"
    config = Settings(
        _env_file=None, postgres_host="db", postgres_user="mcho",
        postgres_password=password, postgres_db="mcho",
    )
    assert make_url(config.sqlalchemy_url).password == password


def test_verified_decision_does_not_publish_automatically():
    event = SimpleNamespace(is_synthetic=False, status="pending_review", verification_status="unverified")
    apply_review_decision(event, "verify")
    assert event.verification_status == "verified"
    assert event.status == "pending_review"


def test_disputing_published_event_removes_it_from_public_status():
    event = SimpleNamespace(is_synthetic=False, status="published", verification_status="verified")
    apply_review_decision(event, "dispute")
    assert event.verification_status == "disputed"
    assert event.status == "corrected"


def test_rejecting_synthetic_fixture_is_blocked():
    event = SimpleNamespace(is_synthetic=True, status="draft", verification_status="unverified")
    with pytest.raises(ValueError):
        apply_review_decision(event, "verify")
