"""UNOSAT damage assessments (HDX), their ~500 m damage grid and refresh log.

Revision ID: 0006_damage_assessments
Revises: 0005_maritime_portwatch
"""
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision = "0006_damage_assessments"
down_revision = "0005_maritime_portwatch"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('damage_assessments',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('country_code', sa.String(length=3), nullable=True),
    sa.Column('unosat_code', sa.String(length=40), nullable=True),
    sa.Column('published_on', sa.Date(), nullable=True),
    sa.Column('imagery_date', sa.Date(), nullable=True),
    sa.Column('resource_url', sa.Text(), nullable=True),
    sa.Column('licence', sa.String(length=160), nullable=False),
    sa.Column('licence_url', sa.Text(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('caveats', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('status_detail', sa.Text(), nullable=True),
    sa.Column('extent', Geometry(geometry_type='POLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('destroyed', sa.Integer(), nullable=True),
    sa.Column('severe', sa.Integer(), nullable=True),
    sa.Column('moderate', sa.Integer(), nullable=True),
    sa.Column('possible', sa.Integer(), nullable=True),
    sa.Column('unclassified', sa.Integer(), nullable=True),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_damage_assessments_country', 'damage_assessments', ['country_code'], unique=False)
    op.create_table('damage_cells',
    sa.Column('assessment_id', sa.String(length=64), nullable=False),
    sa.Column('cell_x', sa.Integer(), nullable=False),
    sa.Column('cell_y', sa.Integer(), nullable=False),
    sa.Column('geometry', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('destroyed', sa.Integer(), nullable=False),
    sa.Column('severe', sa.Integer(), nullable=False),
    sa.Column('moderate', sa.Integer(), nullable=False),
    sa.Column('possible', sa.Integer(), nullable=False),
    sa.Column('unclassified', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['assessment_id'], ['damage_assessments.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('assessment_id', 'cell_x', 'cell_y')
    )
    op.create_table('damage_refreshes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('rows_stored', sa.Integer(), nullable=False),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_damage_refreshes_started_at', 'damage_refreshes', ['started_at'], unique=False)


def downgrade():
    op.drop_table("damage_refreshes")
    op.drop_table("damage_cells")
    op.drop_table("damage_assessments")
