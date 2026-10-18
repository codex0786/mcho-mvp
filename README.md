# MCHO — MENA Conflict & Humanitarian Observatory MVP

An evidence-first geospatial observatory starter. It is designed to connect dated public reporting, human-reviewed event records, satellite scene metadata, and **aggregate** commercial maritime indicators. This repository contains no live conflict feed, provider credentials, or claims about current events. Demo records are explicitly synthetic.

## MVP safety and evidence principles

- Separate reported claims, observations, analytical inferences, and reviewer decisions.
- Every published event must have provenance and a review status.
- Preserve revisions and corrections; do not silently overwrite published facts.
- Satellite change candidates are not automatically verified damage.
- Missing imagery, missing reports, and AIS gaps are not evidence that an event did or did not occur.
- Maritime endpoints expose aggregates only; detailed live vessel tracking is out of scope.
- External connectors remain disabled until provider access, terms, and credentials are configured.

## Stack

- FastAPI + SQLAlchemy 2 + Alembic
- PostgreSQL/PostGIS + Redis
- Celery worker scaffold
- Next.js + TypeScript + MapLibre GL JS
- Docker Compose for local development

## Quick start

1. Copy `.env.example` to `.env` and set a strong local `POSTGRES_PASSWORD` and `REVIEWER_API_KEY`.
2. Start services: `docker compose up --build -d db redis`.
3. Run migrations: `docker compose run --rm api alembic upgrade head`.
4. Start application services: `docker compose up --build api worker web`.
5. API docs: <http://localhost:8000/docs>; web shell: <http://localhost:3000>.

The map uses a configurable MapLibre style URL. If none is configured, the UI displays an explicit configuration state rather than inventing a map provider or key.

## Optional synthetic demo data

After migrations, run:

```bash
docker compose exec api python -m app.seed_demo
```

This inserts only synthetic example records with no real-world incident assertions. They are marked `is_synthetic=true` and `draft` and are not returned by the public published-event endpoint.

## Development

```bash
cd services/api
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
alembic upgrade head
pytest
```

The API requires PostgreSQL/PostGIS for the complete spatial schema. Unit tests should use fixtures/mocks where they do not require a database; integration tests should run against the Compose database.

## Environment variables

See `.env.example`. Keep credentials out of source control. External provider integrations are intentionally unconfigured by default.

## Important limitations

This is an initial implementation scaffold, not a validated production intelligence system. In this environment, Python source compilation and two schema-contract tests passed; a full Docker/Next.js build was not verified because Docker is unavailable and package installation could not complete without network access. Before operational use, complete provider-specific licensing checks, source connectors, identity-provider integration, security review, restore testing, geospatial performance tests, satellite validation, and maritime aggregation validation. Do not use it for targeting or tactical military decisions.
