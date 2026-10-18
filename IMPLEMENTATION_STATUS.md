# Implementation status — starter snapshot

## Implemented in this repository

- FastAPI application and OpenAPI documentation.
- SQLAlchemy/PostGIS-oriented data models for source registry, source documents, events, claims, evidence, revisions, reviews, satellite scenes, humanitarian indicators, maritime aggregates, alerts, and audit records.
- Initial Alembic migration that enables PostGIS and creates the schema.
- Event search with temporal, country, type, and verification filters.
- GeoJSON map endpoint with PostGIS bounding-box filtering and representative points for MapLibre clustering.
- Source registry, imagery scene, humanitarian indicator, and aggregate maritime endpoints.
- OIDC JWT-protected review-task listing, decisions, correction recording, and evidence-gated publication endpoint with reviewer/publisher role gates.
- Synthetic-only demo seed function; public event endpoints exclude synthetic records.
- Celery worker scaffold and connector configuration guards for Copernicus, NASA FIRMS, and a licensed maritime provider.
- Next.js/TypeScript MapLibre UI shell with map status, date/verification filters, event list, and no-live-data notice.
- Docker Compose, environment example, docs, and initial API schema tests.

## Not yet implemented / not validated

- Real provider-specific ingestion and scheduled polling; all provider connectors are intentionally disabled placeholders.
- Actual satellite download, raster preprocessing, change detection, COG generation, and TiTiler deployment.
- AIS passage detection, port geofencing, baseline calculation, and aggregate generation.
- Creation/assignment of review tasks from ingestion and derived observations.
- External OIDC provider setup, browser login/analyst workspace, provider-managed MFA, and operational user/role provisioning. OIDC API validation is implemented but remains unconfigured by default; reviewer endpoints fail closed.
- Alert evaluation/delivery, Prometheus/Grafana dashboards, OpenTelemetry instrumentation, and backup automation.
- Production object storage and raster tile services.
- Antimeridian-crossing bbox support, cursor pagination, map clustering at scale, and spatial query performance benchmarks.
- Full end-to-end, database integration, frontend, security, and load testing.
- Full Docker/Next.js build could not be validated in the current environment.

## Validation performed

- `python -m compileall` passed for API and worker Python files.
- `PYTHONPATH=. pytest -q` in `services/api` passed: 2 tests.
- Full container build and dependency installation not completed due environment limitations; do not interpret the scaffold as production-ready.
