from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import Principal, require_publisher, require_reviewer
from app.db.session import engine, get_db
from app.main import app
from app.models.entities import (
    Event, EventEvidence, EventRevision, EventStatus, ReviewTask, Source, SourceDocument,
    VerificationStatus, utcnow,
)


def _principal(subject: str, *roles: str) -> Principal:
    return Principal(
        subject=subject,
        issuer="https://mcho.test-issuer/",
        roles=frozenset(roles),
    )


@pytest.fixture
def publication_db():
    if os.getenv("MCHO_INTEGRATION_TESTS") != "1":
        pytest.skip("Set MCHO_INTEGRATION_TESTS=1 to run PostgreSQL/PostGIS HTTP integration tests.")
    connection = engine.connect()
    outer_transaction = connection.begin()
    previous_overrides = app.dependency_overrides.copy()

    def override_db():
        session = Session(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, connection
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        outer_transaction.rollback()
        connection.close()


def _seed_candidate(connection):
    now = utcnow()
    editor = "https://mcho.test-issuer/|analyst-01"
    with Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    ) as db:
        source = Source(
            name=f"CI source {uuid4()}",
            source_type="reliefweb_reports",
            access_mode="public_api",
            license_status="approved",
            homepage_url="https://reliefweb.int/",
            license_terms_url="https://reliefweb.int/terms",
            owner_name="Test source owner",
            retention_policy="Store metadata and canonical links only.",
            refresh_cadence="manual",
            terms_reviewed_at=now - timedelta(days=1),
            terms_reviewed_by="https://mcho.test-issuer/|admin-01",
            active=True,
        )
        db.add(source)
        db.flush()

        document = SourceDocument(
            source_id=source.id,
            title="Independent report metadata fixture",
            canonical_url=f"https://reliefweb.int/report/test/{uuid4()}",
            published_at=now - timedelta(hours=2),
            retrieved_at=now - timedelta(hours=1),
            content_hash=uuid4().hex * 2,
            license_note="Metadata-only integration fixture.",
            metadata_json={"test_fixture": True},
            review_status="approved",
            reviewed_by="https://mcho.test-issuer/|doc-reviewer",
            reviewed_at=now - timedelta(minutes=30),
            review_rationale="Source metadata and terms reviewed for integration testing.",
        )
        db.add(document)
        db.flush()

        event = Event(
            event_type="infrastructure_damage",
            summary="A reviewed source reports damage to a public facility.",
            country_code="LB",
            status=EventStatus.pending_review,
            verification_status=VerificationStatus.unverified,
            attribution_status="unknown",
            confidence_label="unassessed",
            spatial_uncertainty_m=1000,
            is_synthetic=False,
        )
        db.add(event)
        db.flush()

        db.add_all([
            EventEvidence(
                event_id=event.id,
                source_document_id=document.id,
                relationship="supports",
                note="Linked as supporting evidence by analyst.",
            ),
            EventRevision(
                event_id=event.id,
                revision_number=1,
                snapshot={
                    "event_type": event.event_type,
                    "summary": event.summary,
                    "country_code": event.country_code,
                    "status": EventStatus.pending_review.value,
                    "verification_status": VerificationStatus.unverified.value,
                },
                changed_by=editor,
                rationale="Analyst created a draft from an approved source document.",
                changed_at=now - timedelta(minutes=10),
            ),
        ])
        task = ReviewTask(
            subject_type="event",
            subject_id=event.id,
            status="pending",
            priority="normal",
        )
        db.add(task)
        db.commit()
        return {
            "event_id": event.id,
            "task_id": task.id,
            "editor_id": editor,
        }


def test_review_publish_requires_three_distinct_principals(publication_db):
    client, connection = publication_db
    candidate = _seed_candidate(connection)
    editor = _principal("analyst-01", "analyst")
    reviewer = _principal("reviewer-02", "reviewer")
    publisher = _principal("publisher-03", "publisher")

    app.dependency_overrides[require_reviewer] = lambda: editor
    same_editor_response = client.post(
        f"/api/v1/reviews/tasks/{candidate['task_id']}/decisions",
        json={"decision": "verify", "rationale": "Compared the source metadata and evidence."},
    )
    assert same_editor_response.status_code == 409
    assert "cannot review their own version" in same_editor_response.json()["detail"]

    app.dependency_overrides[require_reviewer] = lambda: reviewer
    review_response = client.post(
        f"/api/v1/reviews/tasks/{candidate['task_id']}/decisions",
        json={"decision": "verify", "rationale": "Compared the source metadata and evidence."},
    )
    assert review_response.status_code == 201
    assert review_response.json()["verification_status"] == "verified"
    assert review_response.json()["published"] is False

    app.dependency_overrides[require_publisher] = lambda: reviewer
    same_reviewer_response = client.post(f"/api/v1/events/{candidate['event_id']}/publish")
    assert same_reviewer_response.status_code == 409
    assert "reviewer cannot publish" in same_reviewer_response.json()["detail"]

    app.dependency_overrides[require_publisher] = lambda: publisher
    publish_response = client.post(f"/api/v1/events/{candidate['event_id']}/publish")
    assert publish_response.status_code == 200
    payload = publish_response.json()
    assert payload["status"] == "published"
    assert payload["verification_status"] == "verified"
    assert payload["eligible_evidence_count"] == 1
    assert payload["revision_number"] == 1
    assert payload["review_decision_id"]


def test_publication_rejects_a_review_that_predates_latest_revision(publication_db):
    client, connection = publication_db
    candidate = _seed_candidate(connection)
    reviewer = _principal("reviewer-02", "reviewer")
    publisher = _principal("publisher-03", "publisher")
    app.dependency_overrides[require_reviewer] = lambda: reviewer
    review_response = client.post(
        f"/api/v1/reviews/tasks/{candidate['task_id']}/decisions",
        json={"decision": "verify", "rationale": "Compared the source metadata and evidence."},
    )
    assert review_response.status_code == 201

    with Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    ) as db:
        db.add(EventRevision(
            event_id=candidate["event_id"],
            revision_number=2,
            snapshot={"summary": "A corrected summary requiring a fresh review."},
            changed_by="https://mcho.test-issuer/|correction-editor-04",
            rationale="A material correction was introduced after review.",
            changed_at=utcnow() + timedelta(minutes=1),
        ))
        db.commit()

    app.dependency_overrides[require_publisher] = lambda: publisher
    response = client.post(f"/api/v1/events/{candidate['event_id']}/publish")
    assert response.status_code == 409
    assert "after the latest event revision" in response.json()["detail"]
