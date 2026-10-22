"""IMF PortWatch maritime aggregates: areas, refresh log, unique daily metrics.

Revision ID: 0005_maritime_portwatch
Revises: 0004_thermal_history
"""
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision = "0005_maritime_portwatch"
down_revision = "0004_thermal_history"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('maritime_areas',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('country_code', sa.String(length=3), nullable=True),
    sa.Column('geometry', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('reference_vessels_per_year', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('maritime_refreshes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('rows_stored', sa.Integer(), nullable=False),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_maritime_refreshes_started_at', 'maritime_refreshes', ['started_at'], unique=False)
    op.create_unique_constraint("uq_maritime_aggregate_metric", "maritime_aggregates", ["area_id", "period_start", "metric"])


def downgrade():
    op.drop_constraint("uq_maritime_aggregate_metric", "maritime_aggregates", type_="unique")
    op.drop_table("maritime_refreshes")
    op.drop_table("maritime_areas")
