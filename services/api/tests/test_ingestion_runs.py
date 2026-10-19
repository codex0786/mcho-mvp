import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.ingestion_runs import STALE_RUN_SUMMARY, expire_stale_runs, run_is_stale
from app.db.session import engine
from app.models.entities import AuditLog, IngestionRun, Source, utcnow

TIMEOUT = timedelta(minutes=60)


def _run(status, minutes_since_start=None, minutes_since_created=5):
    now = utcnow()
    return SimpleNamespace(
        status=status,
        created_at=now - timedelta(minutes=minutes_since_created),
        started_at=None if minutes_since_start is None else now - timedelta(minutes=minutes_since_start),
    )


def test_running_run_past_timeout_is_stale():
    assert run_is_stale(_run("running", minutes_since_start=61), utcnow(), TIMEOUT)


def test_recently_started_run_is_not_stale():
    assert not run_is_stale(_run("running", minutes_since_start=5), utcnow(), TIMEOUT)


def test_never_started_queued_run_uses_creation_time():
    assert run_is_stale(_run("queued", minutes_since_created=90), utcnow(), TIMEOUT)
    assert not run_is_stale(_run("queued", minutes_since_created=10), utcnow(), TIMEOUT)


@pytest.mark.parametrize("status", ["completed", "failed", "skipped", "partial", "queue_failed"])
def test_finished_runs_are_never_stale(status):
    assert not run_is_stale(_run(status, minutes_since_start=600), utcnow(), TIMEOUT)


@pytest.fixture
def db_session():
    if os.getenv("MCHO_INTEGRATION_TESTS") != "1":
        pytest.skip("Set MCHO_INTEGRATION_TESTS=1 to run PostgreSQL/PostGIS integration tests.")
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def test_expire_stale_runs_frees_the_source_for_a_new_run(db_session):
    now = utcnow()
    source = Source(name=f"Stale-run source {uuid4()}", source_type="reliefweb_reports")
    db_session.add(source)
    db_session.flush()
    stuck = IngestionRun(source_id=source.id, status="running", adapter_name="reliefweb_reports",
                         created_at=now - timedelta(hours=3), started_at=now - timedelta(hours=3))
    db_session.add(stuck)
    db_session.flush()

    assert expire_stale_runs(db_session, source.id, now) == 1
    db_session.flush()
    assert stuck.status == "failed"
    assert stuck.error_summary == STALE_RUN_SUMMARY
    assert db_session.query(AuditLog).filter_by(subject_id=str(stuck.id), action="ingestion_run_expired").count() == 1

    # The partial unique index on active runs now admits a new run for the source.
    db_session.add(IngestionRun(source_id=source.id, status="queued", adapter_name="reliefweb_reports"))
    db_session.flush()


def test_expire_stale_runs_leaves_live_runs_alone(db_session):
    source = Source(name=f"Live-run source {uuid4()}", source_type="reliefweb_reports")
    db_session.add(source)
    db_session.flush()
    live = IngestionRun(source_id=source.id, status="running", adapter_name="reliefweb_reports",
                        started_at=utcnow() - timedelta(minutes=2))
    db_session.add(live)
    db_session.flush()
    assert expire_stale_runs(db_session, source.id) == 0
    assert live.status == "running"
