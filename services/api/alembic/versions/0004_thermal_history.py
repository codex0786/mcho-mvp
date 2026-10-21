"""Last-year FIRMS archive counts for year-on-year comparison.

Revision ID: 0004_thermal_history
Revises: 0003_thermal_detections
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_thermal_history"
down_revision = "0003_thermal_detections"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('thermal_history_daily',
    sa.Column('country_code', sa.String(length=3), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('product', sa.String(length=40), nullable=False),
    sa.Column('detections', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['country_code'], ['country_boundaries.iso_a3'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('country_code', 'day', 'product')
    )
    op.create_table('thermal_history_fetches',
    sa.Column('product', sa.String(length=40), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('source_product', sa.String(length=40), nullable=False),
    sa.Column('rows', sa.Integer(), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('product', 'day')
    )


def downgrade():
    op.drop_table("thermal_history_fetches")
    op.drop_table("thermal_history_daily")
