"""Add source registry governance and ingestion-run/checkpoint tables.

Revision ID: 0002_ingestion_framework
Revises: 0001_initial
"""
from alembic import op
from sqlalchemy import text

from app.db.session import Base
from app.models import entities  # noqa: F401

revision = "0002_ingestion_framework"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # The original 0001 migration used metadata.create_all. This creates the new
    # ingestion tables for older installations without disturbing existing data.
    Base.metadata.create_all(
        bind=bind,
        tables=[
            entities.IngestionRun.__table__,
            entities.IngestionError.__table__,
            entities.SourceCheckpoint.__table__,
            entities.SourceRecord.__table__,
        ],
        checkfirst=True,
    )
    op.execute(text("ALTER TABLE sources ADD COLUMN IF NOT EXISTS license_terms_url TEXT"))
    op.execute(text("ALTER TABLE sources ADD COLUMN IF NOT EXISTS owner_name VARCHAR(240)"))
    op.execute(text("ALTER TABLE sources ADD COLUMN IF NOT EXISTS retention_policy TEXT"))
    op.execute(text("ALTER TABLE sources ADD COLUMN IF NOT EXISTS refresh_cadence VARCHAR(80) NOT NULL DEFAULT 'manual'"))
    op.execute(text("ALTER TABLE sources ADD COLUMN IF NOT EXISTS terms_reviewed_at TIMESTAMPTZ"))
    op.execute(text("ALTER TABLE sources ADD COLUMN IF NOT EXISTS terms_reviewed_by VARCHAR(240)"))
    op.execute(text("ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS review_status VARCHAR(40) NOT NULL DEFAULT 'pending_review'"))
    op.execute(text("ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(240)"))
    op.execute(text("ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ"))
    op.execute(text("ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS review_rationale TEXT"))
    op.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_ingestion_run_active_source "
        "ON ingestion_runs (source_id) WHERE status IN ('queued', 'running', 'retrying')"
    ))
    # Existing publications predate the per-document review gate. Fail closed on
    # upgrade: keep them out of public APIs until an editor re-reviews each document,
    # re-approves the source terms and republishes the event through the API.
    op.execute(text("""
        UPDATE events AS e
        SET status = 'corrected'
        WHERE e.status = 'published'
          AND NOT EXISTS (
              SELECT 1
              FROM event_evidence AS ee
              JOIN source_documents AS sd ON sd.id = ee.source_document_id
              JOIN sources AS s ON s.id = sd.source_id
              WHERE ee.event_id = e.id
                AND sd.review_status = 'approved'
                AND s.active IS TRUE
                AND s.license_status IN ('approved', 'public_domain', 'open_license', 'licensed')
                AND s.terms_reviewed_at IS NOT NULL
                AND s.terms_reviewed_by IS NOT NULL
                AND s.license_terms_url IS NOT NULL
                AND s.retention_policy IS NOT NULL
          )
    """))


def downgrade():
    bind = op.get_bind()
    op.execute(text("DROP INDEX IF EXISTS uq_ingestion_run_active_source"))
    op.execute(text("ALTER TABLE source_documents DROP COLUMN IF EXISTS review_rationale"))
    op.execute(text("ALTER TABLE source_documents DROP COLUMN IF EXISTS reviewed_at"))
    op.execute(text("ALTER TABLE source_documents DROP COLUMN IF EXISTS reviewed_by"))
    op.execute(text("ALTER TABLE source_documents DROP COLUMN IF EXISTS review_status"))
    op.execute(text("ALTER TABLE sources DROP COLUMN IF EXISTS terms_reviewed_by"))
    op.execute(text("ALTER TABLE sources DROP COLUMN IF EXISTS terms_reviewed_at"))
    op.execute(text("ALTER TABLE sources DROP COLUMN IF EXISTS refresh_cadence"))
    op.execute(text("ALTER TABLE sources DROP COLUMN IF EXISTS retention_policy"))
    op.execute(text("ALTER TABLE sources DROP COLUMN IF EXISTS owner_name"))
    op.execute(text("ALTER TABLE sources DROP COLUMN IF EXISTS license_terms_url"))
    Base.metadata.drop_all(
        bind=bind,
        tables=[
            entities.SourceCheckpoint.__table__,
            entities.SourceRecord.__table__,
            entities.IngestionError.__table__,
            entities.IngestionRun.__table__,
        ],
        checkfirst=True,
    )
