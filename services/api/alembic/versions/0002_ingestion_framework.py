"""Add source registry governance and ingestion-run/checkpoint tables.

Revision ID: 0002_ingestion_framework
Revises: 0001_initial
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0002_ingestion_framework"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # Databases bootstrapped by the legacy create_all-based 0001 may already
    # contain these tables, so each one is created only when absent. The DDL is
    # explicit and frozen here; it must not be derived from the live models.
    existing = set(sa.inspect(bind).get_table_names())
    if "ingestion_runs" not in existing:
        op.create_table("ingestion_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.String(length=160), nullable=True),
        sa.Column("trigger", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("adapter_name", sa.String(length=120), nullable=False),
        sa.Column("adapter_version", sa.String(length=80), nullable=False),
        sa.Column("requested_by", sa.String(length=240), nullable=True),
        sa.Column("cursor_in", sa.JSON(), nullable=False),
        sa.Column("cursor_out", sa.JSON(), nullable=False),
        sa.Column("pages_fetched", sa.Integer(), nullable=False),
        sa.Column("records_fetched", sa.Integer(), nullable=False),
        sa.Column("records_created", sa.Integer(), nullable=False),
        sa.Column("records_updated", sa.Integer(), nullable=False),
        sa.Column("records_unchanged", sa.Integer(), nullable=False),
        sa.Column("records_failed", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id")
        )
        op.create_index("ix_ingestion_runs_source_created", "ingestion_runs", ["source_id", "created_at"], unique=False)
        op.create_index("ix_ingestion_runs_status", "ingestion_runs", ["status"], unique=False)
    if "ingestion_errors" not in existing:
        op.create_table("ingestion_errors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=False),
        sa.Column("row_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ingestion_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id")
        )
        op.create_index("ix_ingestion_errors_run_created", "ingestion_errors", ["run_id", "created_at"], unique=False)
    if "source_checkpoints" not in existing:
        op.create_table("source_checkpoints",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("last_run_id", sa.UUID(), nullable=True),
        sa.Column("cursor_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["last_run_id"], ["ingestion_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id")
        )
    if "source_records" not in existing:
        op.create_table("source_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("source_document_id", sa.UUID(), nullable=False),
        sa.Column("latest_content_hash", sa.String(length=128), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "external_id", name="uq_source_record_external_id")
        )
        op.create_index("ix_source_records_last_seen", "source_records", ["last_seen_at"], unique=False)
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
    for table in ("source_records", "source_checkpoints", "ingestion_errors", "ingestion_runs"):
        op.execute(text(f"DROP TABLE IF EXISTS {table}"))
