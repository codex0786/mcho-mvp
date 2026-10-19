"""Initial MCHO schema.

Revision ID: 0001_initial
Revises:

Explicit DDL frozen at this revision. Earlier checkouts used
``Base.metadata.create_all`` here, which made a fresh database's schema depend
on whatever the models looked like at install time rather than on the
migration history. Databases already stamped at 0001 are unaffected because
Alembic never re-runs an applied revision; columns and tables added later are
created by subsequent revisions.
"""
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

ENUM_TYPES = ("event_status", "verification_status")
TABLES_IN_DROP_ORDER = (
    "audit_log", "alerts", "humanitarian_indicators", "maritime_aggregates", "satellite_scenes",
    "review_decisions", "review_tasks", "event_revisions", "event_evidence", "claims", "events",
    "source_documents", "sources",
)


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table('sources',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=240), nullable=False),
    sa.Column('source_type', sa.String(length=60), nullable=False),
    sa.Column('access_mode', sa.String(length=60), nullable=False),
    sa.Column('license_status', sa.String(length=60), nullable=False),
    sa.Column('homepage_url', sa.Text(), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('source_documents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('source_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('canonical_url', sa.Text(), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('content_hash', sa.String(length=128), nullable=False),
    sa.Column('license_note', sa.Text(), nullable=True),
    sa.Column('metadata_json', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_id', 'content_hash', name='uq_source_document_hash')
    )
    op.create_table('events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('event_type', sa.String(length=80), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('event_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('event_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('country_code', sa.String(length=2), nullable=True),
    sa.Column('status', sa.Enum('draft', 'pending_review', 'published', 'corrected', 'withdrawn', name='event_status'), nullable=False),
    sa.Column('verification_status', sa.Enum('unverified', 'provisional', 'verified', 'disputed', 'rejected', name='verification_status'), nullable=False),
    sa.Column('attribution_status', sa.String(length=40), nullable=False),
    sa.Column('confidence_label', sa.String(length=40), nullable=False),
    sa.Column('spatial_uncertainty_m', sa.Integer(), nullable=True),
    sa.Column('geometry', Geometry(srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('is_synthetic', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('claims',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('event_id', sa.UUID(), nullable=False),
    sa.Column('claim_text', sa.Text(), nullable=False),
    sa.Column('claim_type', sa.String(length=80), nullable=False),
    sa.Column('attribution_status', sa.String(length=40), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('event_evidence',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('event_id', sa.UUID(), nullable=False),
    sa.Column('source_document_id', sa.UUID(), nullable=False),
    sa.Column('relationship', sa.String(length=40), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_document_id'], ['source_documents.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id', 'source_document_id', 'relationship', name='uq_event_evidence_link')
    )
    op.create_table('event_revisions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('event_id', sa.UUID(), nullable=False),
    sa.Column('revision_number', sa.Integer(), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('changed_by', sa.String(length=160), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=False),
    sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id', 'revision_number', name='uq_event_revision_number')
    )
    op.create_table('review_tasks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('subject_type', sa.String(length=60), nullable=False),
    sa.Column('subject_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('priority', sa.String(length=30), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('review_decisions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('task_id', sa.UUID(), nullable=False),
    sa.Column('reviewer_id', sa.String(length=160), nullable=False),
    sa.Column('decision', sa.String(length=60), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['task_id'], ['review_tasks.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('satellite_scenes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('provider', sa.String(length=120), nullable=False),
    sa.Column('mission', sa.String(length=120), nullable=True),
    sa.Column('acquired_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('footprint', Geometry(geometry_type='POLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('asset_uri', sa.Text(), nullable=True),
    sa.Column('access_status', sa.String(length=40), nullable=False),
    sa.Column('quality_metadata', sa.JSON(), nullable=False),
    sa.Column('license_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('maritime_aggregates',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('area_id', sa.String(length=120), nullable=False),
    sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('metric', sa.String(length=80), nullable=False),
    sa.Column('value', sa.Double(), nullable=False),
    sa.Column('unit', sa.String(length=40), nullable=False),
    sa.Column('coverage_fraction', sa.Double(), nullable=True),
    sa.Column('source_version', sa.String(length=120), nullable=False),
    sa.Column('quality_flags', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('humanitarian_indicators',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('indicator_type', sa.String(length=100), nullable=False),
    sa.Column('geography_id', sa.String(length=120), nullable=False),
    sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('value', sa.Double(), nullable=True),
    sa.Column('unit', sa.String(length=60), nullable=False),
    sa.Column('estimate_status', sa.String(length=40), nullable=False),
    sa.Column('source_document_id', sa.UUID(), nullable=True),
    sa.Column('quality_flags', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['source_document_id'], ['source_documents.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('alerts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('rule_id', sa.String(length=120), nullable=False),
    sa.Column('subject_type', sa.String(length=80), nullable=False),
    sa.Column('subject_id', sa.UUID(), nullable=True),
    sa.Column('severity', sa.String(length=30), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('audit_log',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('actor_id', sa.String(length=160), nullable=False),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('subject_type', sa.String(length=80), nullable=False),
    sa.Column('subject_id', sa.String(length=160), nullable=False),
    sa.Column('detail', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_events_event_start', 'events', ['event_start'], unique=False)
    op.create_index('ix_events_geometry', 'events', ['geometry'], unique=False, postgresql_using='gist')
    op.create_index('ix_events_status', 'events', ['status'], unique=False)
    op.create_index('ix_events_verification_status', 'events', ['verification_status'], unique=False)
    op.create_index('ix_maritime_area_period', 'maritime_aggregates', ['area_id', 'period_start', 'period_end'], unique=False)


def downgrade():
    for table in TABLES_IN_DROP_ORDER:
        op.drop_table(table)
    for enum_name in ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
    # The postgis extension is left installed: other schemas may depend on it.
