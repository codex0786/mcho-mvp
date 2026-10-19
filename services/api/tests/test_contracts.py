from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import Settings, settings
from app.core.review_policy import apply_review_decision
from app.core.security import Principal, get_current_principal, require_reviewer, require_publisher
from app.schemas.events import CorrectionIn, EventOut, ReviewDecisionIn, EventDraftFromDocumentIn
from app.schemas.sources import SourceCreateIn, SourcePatchIn


def test_review_decision_accepts_only_known_values():
    valid = ReviewDecisionIn(decision="verify", rationale="Compared two independent source records.")
    assert valid.decision == "verify"
    with pytest.raises(ValidationError):
        ReviewDecisionIn(decision="publish_anything", rationale="This should not be accepted")
    with pytest.raises(ValidationError):
        ReviewDecisionIn(decision="verify", rationale="short")


def test_source_registration_requires_https_terms_url():
    valid = SourceCreateIn(
        name="ReliefWeb MENA", source_type="reliefweb_reports",
        homepage_url="https://reliefweb.int", license_terms_url="https://reliefweb.int/terms",
        retention_policy="Store provider metadata and canonical source link only.",
    )
    assert str(valid.license_terms_url).startswith("https://")
    with pytest.raises(ValidationError):
        SourceCreateIn(
            name="Unsafe URL Source", source_type="reliefweb_reports",
            license_terms_url="http://example.org/terms",
        )


def test_source_activation_requires_explicit_licence_state():
    with pytest.raises(ValidationError):
        SourcePatchIn(license_status="not_reviewed")
    with pytest.raises(ValidationError):
        SourcePatchIn(active=None)


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


def test_reviewer_authentication_fails_closed_when_oidc_is_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "oidc_issuer", "")
    monkeypatch.setattr(settings, "oidc_audience", "")
    monkeypatch.setattr(settings, "oidc_jwks_url", "")
    with pytest.raises(HTTPException) as exc:
        get_current_principal(authorization=None)
    assert exc.value.status_code == 503


def _rsa_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _configure_oidc(monkeypatch, public_key):
    monkeypatch.setattr(settings, "oidc_issuer", "https://issuer.example.test/")
    monkeypatch.setattr(settings, "oidc_audience", "mcho-api")
    monkeypatch.setattr(settings, "oidc_jwks_url", "https://issuer.example.test/.well-known/jwks.json")
    monkeypatch.setattr(settings, "oidc_role_claim", "realm_access.roles")
    monkeypatch.setattr(settings, "oidc_algorithms", "RS256")
    monkeypatch.setattr(settings, "app_env", "test")

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, token):
            return SimpleNamespace(key=public_key)

    monkeypatch.setattr("app.core.security._jwks_client", lambda url: FakeJwksClient())


def test_valid_oidc_access_token_yields_principal_and_roles(monkeypatch):
    private_key, public_key = _rsa_pair()
    _configure_oidc(monkeypatch, public_key)
    now = datetime.now(timezone.utc)
    token = jwt.encode({
        "iss": "https://issuer.example.test/", "aud": "mcho-api", "sub": "user-123",
        "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=5)).timestamp()),
        "realm_access": {"roles": ["reviewer", "analyst"]},
    }, private_key, algorithm="RS256", headers={"kid": "test-key"})

    principal = get_current_principal(authorization=f"Bearer {token}")
    assert principal.subject == "user-123"
    assert principal.roles == frozenset({"reviewer", "analyst"})
    assert principal.issuer == "https://issuer.example.test/"
    assert principal.identity == "https://issuer.example.test/|user-123"


def test_oidc_access_token_with_wrong_audience_is_rejected(monkeypatch):
    private_key, public_key = _rsa_pair()
    _configure_oidc(monkeypatch, public_key)
    now = datetime.now(timezone.utc)
    token = jwt.encode({
        "iss": "https://issuer.example.test/", "aud": "another-api", "sub": "user-123",
        "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=5)).timestamp()),
        "realm_access": {"roles": ["reviewer"]},
    }, private_key, algorithm="RS256", headers={"kid": "test-key"})

    with pytest.raises(HTTPException) as exc:
        get_current_principal(authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


def test_role_guard_rejects_analyst_from_publishing():
    principal = Principal(subject="analyst-1", issuer="https://issuer.example.test/", roles=frozenset({"analyst"}))
    with pytest.raises(HTTPException) as exc:
        require_publisher(principal=principal)
    assert exc.value.status_code == 403


def test_role_guard_allows_reviewer_for_review_decisions():
    principal = Principal(subject="reviewer-1", issuer="https://issuer.example.test/", roles=frozenset({"reviewer"}))
    assert require_reviewer(principal=principal) == principal


def test_managed_postgres_dsn_selects_installed_psycopg_driver():
    config = Settings(_env_file=None, database_url="postgresql://demo:password@db.internal:5432/mcho")
    assert config.sqlalchemy_url == "postgresql+psycopg://demo:password@db.internal:5432/mcho"


def test_postgres_legacy_url_scheme_is_normalized():
    config = Settings(_env_file=None, database_url="postgres://demo:password@db.internal:5432/mcho")
    assert config.sqlalchemy_url.startswith("postgresql+psycopg://")


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



def test_event_draft_requires_explicit_source_summary_and_uncertain_location():
    draft = EventDraftFromDocumentIn(
        event_type="infrastructure_damage",
        summary="A reviewed source reports damage to a public building.",
        event_start="2026-10-18T08:00:00Z",
        country_code="LB",
        latitude=33.89,
        longitude=35.50,
        spatial_uncertainty_m=1500,
        rationale="Drafted from a reviewed source; exact damage attribution remains unverified.",
    )
    assert draft.country_code == "LB"
    assert draft.spatial_uncertainty_m == 1500


def test_event_draft_rejects_point_without_uncertainty_or_partial_coordinates():
    with pytest.raises(ValidationError):
        EventDraftFromDocumentIn(
            event_type="infrastructure_damage",
            summary="A reviewed source reports damage to a public building.",
            latitude=33.89,
            longitude=35.50,
            rationale="Location precision was not assessed from the source.",
        )
    with pytest.raises(ValidationError):
        EventDraftFromDocumentIn(
            event_type="infrastructure_damage",
            summary="A reviewed source reports damage to a public building.",
            latitude=33.89,
            spatial_uncertainty_m=500,
            rationale="Only one coordinate is known; do not imply a precise point.",
        )


def test_event_draft_rejects_naive_timestamps_and_reversed_ranges():
    with pytest.raises(ValidationError):
        EventDraftFromDocumentIn(
            event_type="armed_clash_reported",
            summary="A source reports a clash in the area.",
            event_start="2026-10-18T08:00:00",
            rationale="The source timestamp lacks an explicit timezone offset.",
        )
    with pytest.raises(ValidationError):
        EventDraftFromDocumentIn(
            event_type="armed_clash_reported",
            summary="A source reports a clash in the area.",
            event_start="2026-10-18T08:00:00Z",
            event_end="2026-10-17T08:00:00Z",
            rationale="The time range is intentionally invalid for validation testing.",
        )


def test_event_draft_rejects_invalid_country_codes_and_event_taxonomy():
    with pytest.raises(ValidationError):
        EventDraftFromDocumentIn(
            event_type="infrastructure_damage",
            summary="A reviewed source reports damage to a public building.",
            country_code="lb",
            rationale="Country code must follow the uppercase ISO alpha-2 convention.",
        )
    with pytest.raises(ValidationError):
        EventDraftFromDocumentIn(
            event_type="unreviewed_source_is_the_truth",
            summary="A reviewed source reports damage to a public building.",
            rationale="Event taxonomy is a controlled classification.",
        )
