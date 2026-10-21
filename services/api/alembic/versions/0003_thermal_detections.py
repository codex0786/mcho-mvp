"""Satellite thermal detections (NASA FIRMS) and MENA country borders.

Revision ID: 0003_thermal_detections
Revises: 0002_ingestion_framework

Country borders come from Natural Earth 1:50m Admin 0 (public domain), filtered
to the countries MCHO reports on and frozen in alembic/data so this revision
always loads the same geometry.
"""
import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision = "0003_thermal_detections"
down_revision = "0002_ingestion_framework"
branch_labels = None
depends_on = None

BOUNDARIES_FILE = Path(__file__).resolve().parents[1] / "data" / "mena_countries_ne50m.geojson"


def upgrade():
    op.create_table('country_boundaries',
    sa.Column('iso_a3', sa.String(length=3), nullable=False),
    sa.Column('iso_a2', sa.String(length=2), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('geometry', Geometry(geometry_type='MULTIPOLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.PrimaryKeyConstraint('iso_a3')
    )
    op.create_table('thermal_detections',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('product', sa.String(length=40), nullable=False),
    sa.Column('satellite', sa.String(length=20), nullable=False),
    sa.Column('instrument', sa.String(length=20), nullable=False),
    sa.Column('acquired_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('latitude', sa.Double(), nullable=False),
    sa.Column('longitude', sa.Double(), nullable=False),
    sa.Column('geometry', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('country_code', sa.String(length=3), nullable=False),
    sa.Column('brightness_ti4', sa.Double(), nullable=True),
    sa.Column('brightness_ti5', sa.Double(), nullable=True),
    sa.Column('frp', sa.Double(), nullable=True),
    sa.Column('scan', sa.Double(), nullable=True),
    sa.Column('track', sa.Double(), nullable=True),
    sa.Column('confidence', sa.String(length=10), nullable=False),
    sa.Column('daynight', sa.String(length=1), nullable=False),
    sa.Column('version', sa.String(length=20), nullable=False),
    sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['country_code'], ['country_boundaries.iso_a3'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('product', 'acquired_at', 'latitude', 'longitude', name='uq_thermal_detection_observation')
    )
    op.create_table('thermal_refreshes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('rows_received', sa.Integer(), nullable=False),
    sa.Column('rows_stored', sa.Integer(), nullable=False),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_country_boundaries_geometry', 'country_boundaries', ['geometry'], unique=False, postgresql_using='gist')
    op.create_index('ix_thermal_detections_acquired_at', 'thermal_detections', ['acquired_at'], unique=False)
    op.create_index('ix_thermal_detections_country_acquired', 'thermal_detections', ['country_code', 'acquired_at'], unique=False)
    op.create_index('ix_thermal_detections_geometry', 'thermal_detections', ['geometry'], unique=False, postgresql_using='gist')
    op.create_index('ix_thermal_refreshes_started_at', 'thermal_refreshes', ['started_at'], unique=False)

    features = json.loads(BOUNDARIES_FILE.read_text(encoding="utf-8"))["features"]
    insert = sa.text(
        "INSERT INTO country_boundaries (iso_a3, iso_a2, name, geometry) "
        "VALUES (:iso_a3, :iso_a2, :name, "
        "ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326)), 3)))"
    )
    bind = op.get_bind()
    for feature in features:
        properties = feature["properties"]
        bind.execute(insert, {
            "iso_a3": properties["iso_a3"], "iso_a2": properties["iso_a2"], "name": properties["name"],
            "geometry": json.dumps(feature["geometry"]),
        })


def downgrade():
    op.drop_table("thermal_refreshes")
    op.drop_table("thermal_detections")
    op.drop_table("country_boundaries")
