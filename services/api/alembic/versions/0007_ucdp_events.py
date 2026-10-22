"""UCDP Candidate events for MENA with satellite heat cross-checks; release and refresh logs.

Revision ID: 0007_ucdp_events
Revises: 0006_damage_assessments
"""
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision = "0007_ucdp_events"
down_revision = "0006_damage_assessments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('ucdp_events',
    sa.Column('id', sa.BigInteger(), autoincrement=False, nullable=False),
    sa.Column('relid', sa.String(length=64), nullable=False),
    sa.Column('release', sa.String(length=20), nullable=False),
    sa.Column('type_of_violence', sa.SmallInteger(), nullable=False),
    sa.Column('conflict_name', sa.Text(), nullable=False),
    sa.Column('dyad_name', sa.Text(), nullable=False),
    sa.Column('side_a', sa.Text(), nullable=False),
    sa.Column('side_b', sa.Text(), nullable=False),
    sa.Column('where_description', sa.Text(), nullable=True),
    sa.Column('adm_1', sa.Text(), nullable=True),
    sa.Column('ucdp_country', sa.String(length=120), nullable=False),
    sa.Column('country_code', sa.String(length=3), nullable=False),
    sa.Column('latitude', sa.Double(), nullable=False),
    sa.Column('longitude', sa.Double(), nullable=False),
    sa.Column('geometry', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('date_start', sa.Date(), nullable=False),
    sa.Column('date_end', sa.Date(), nullable=False),
    sa.Column('date_prec', sa.SmallInteger(), nullable=False),
    sa.Column('where_prec', sa.SmallInteger(), nullable=False),
    sa.Column('event_clarity', sa.SmallInteger(), nullable=True),
    sa.Column('code_status', sa.String(length=60), nullable=True),
    sa.Column('deaths_best', sa.Integer(), nullable=False),
    sa.Column('deaths_low', sa.Integer(), nullable=False),
    sa.Column('deaths_high', sa.Integer(), nullable=False),
    sa.Column('deaths_civilians', sa.Integer(), nullable=False),
    sa.Column('number_of_sources', sa.Integer(), nullable=True),
    sa.Column('heat_status', sa.String(length=20), nullable=False),
    sa.Column('heat_detections', sa.Integer(), nullable=True),
    sa.Column('heat_persistent_excluded', sa.Integer(), nullable=True),
    sa.Column('heat_max_frp', sa.Double(), nullable=True),
    sa.Column('heat_nearest_km', sa.Double(), nullable=True),
    sa.Column('heat_radius_km', sa.Double(), nullable=True),
    sa.Column('heat_products', sa.String(length=120), nullable=True),
    sa.Column('heat_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ucdp_events_date_start', 'ucdp_events', ['date_start'], unique=False)
    op.create_index('ix_ucdp_events_country', 'ucdp_events', ['country_code'], unique=False)
    op.create_index('ix_ucdp_events_heat_status', 'ucdp_events', ['heat_status'], unique=False)
    op.create_table('ucdp_releases',
    sa.Column('release', sa.String(length=20), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('etag', sa.String(length=200), nullable=True),
    sa.Column('last_modified', sa.String(length=80), nullable=True),
    sa.Column('rows_total', sa.Integer(), nullable=False),
    sa.Column('rows_mena', sa.Integer(), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('release')
    )
    op.create_table('ucdp_refreshes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('rows_stored', sa.Integer(), nullable=False),
    sa.Column('heat_checked', sa.Integer(), nullable=False),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ucdp_refreshes_started_at', 'ucdp_refreshes', ['started_at'], unique=False)


def downgrade():
    op.drop_table("ucdp_refreshes")
    op.drop_table("ucdp_releases")
    op.drop_table("ucdp_events")
