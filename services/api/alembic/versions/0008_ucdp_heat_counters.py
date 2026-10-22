"""Record FIRMS requests and detections fetched per UCDP heat cross-check run.

Revision ID: 0008_ucdp_heat_counters
Revises: 0007_ucdp_events
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_ucdp_heat_counters"
down_revision = "0007_ucdp_events"
branch_labels = None
depends_on = None


def upgrade():
    # Existing rows predate the counters; 0 is filled only to satisfy NOT NULL, then the default is dropped.
    for column in ("heat_requests", "heat_detections_fetched"):
        op.add_column("ucdp_refreshes", sa.Column(column, sa.Integer(), nullable=False, server_default="0"))
        op.alter_column("ucdp_refreshes", column, server_default=None)


def downgrade():
    op.drop_column("ucdp_refreshes", "heat_detections_fetched")
    op.drop_column("ucdp_refreshes", "heat_requests")
