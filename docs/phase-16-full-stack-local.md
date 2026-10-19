# Phase 16 — Full-stack local development

## Purpose

Provide an opt-in local stack for testing the actual MCHO web app, API, PostgreSQL/PostGIS database, Redis and background worker together. This is separate from the faster frontend-only preview command.

## Requirements

- Docker Desktop with Docker Compose v2, with the Docker engine running.
- Python 3 and curl on the host for setup validation and the smoke-test script.
- Enough disk space and memory to build and run the API, worker and Next.js containers.

## Start

From the repository root:

```bash
bash scripts/start-local-stack.sh
```

If `.env` does not exist, the script copies `.env.example`, generates a random local PostgreSQL password with Python's `secrets` module, and sets the file permissions to user-only on Unix. It never overwrites an existing `.env`; if an existing file still has the template password, the script fails and asks you to fix it.

The script starts PostGIS and Redis, applies database migrations, builds and starts the API/worker/web containers, waits for API and web readiness, inserts idempotent unpublished synthetic fixture data, and runs `scripts/smoke-test.sh`.

## Local URLs

- Prototype: `http://127.0.0.1:3000/demo`
- Application: `http://127.0.0.1:3000/`
- API documentation: `http://127.0.0.1:8000/docs`
- Analyst workspace: `http://127.0.0.1:3000/analyst` (sign-in requires an OIDC provider and matching settings).

Compose publishes the web and API ports on `127.0.0.1` only. The PostgreSQL and Redis ports are not published to the host. Live source connectors remain disabled unless configured and approved separately.

## Stop and reset

Stop containers while preserving database/cache volumes:

```bash
docker compose down
```

Persistent local data remains in named volumes. Deleting the volumes is destructive; do not use `docker compose down -v` unless you deliberately want to erase the local database and Redis state.

## Validation and troubleshooting

The script checks `/api/v1/health/ready` for database/PostGIS/Redis readiness and `/demo` for the web route, then verifies API health, the published-event and GeoJSON response shapes, runtime public config and same-origin proxy using the smoke test. If a readiness check fails, the script prints service status and recent logs; inspect `docker compose logs --tail=100 api web db redis` before retrying.

A passing smoke test confirms local service wiring only. It does not validate a real identity provider, source licensing, live data accuracy, production operations, or external-source activation.
