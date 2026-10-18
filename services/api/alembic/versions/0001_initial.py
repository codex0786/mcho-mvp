"""Initial MCHO schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
from app.db.session import Base
from app.models import entities  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    Base.metadata.create_all(bind=op.get_bind())


def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())
