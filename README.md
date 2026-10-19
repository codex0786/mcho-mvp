# MCHO — MENA Conflict & Humanitarian Observatory MVP

An evidence-first geospatial observatory starter. It is designed to connect dated public reporting, human-reviewed event records, satellite scene metadata, and **aggregate** commercial maritime indicators. This repository contains no enabled live conflict feed or committed provider credentials and makes no claims about current events. Demo records are explicitly synthetic.

## MVP safety and evidence principles

- Separate reported claims, observations, analytical inferences, and reviewer decisions.
- Every published event must have provenance and a review status.
- Preserve revisions and corrections; do not silently overwrite published facts.
- Satellite change candidates are not automatically verified damage.
- Missing imagery, missing reports, and AIS gaps are not evidence that an event did or did not occur.
- Maritime endpoints expose aggregates only; detailed live vessel tracking is out of scope.
- External connectors remain disabled until provider access, terms and credentials are configured; ReliefWeb additionally requires an approved app name and explicit country scope.

## Stack

- FastAPI + SQLAlchemy 2 + Alembic
- PostgreSQL/PostGIS + Redis
- Celery worker scaffold
- Next.js + TypeScript + MapLibre GL JS
- Docker Compose for local development

## Fast preview: interactive UI without Docker

Before starting the full stack, preview the actual interactive prototype with one command from the repository root:

```bash
bash scripts/start-interactive-demo.sh
```

Then open <http://127.0.0.1:3000/demo>. The launcher installs frontend dependencies if needed and starts only Next.js. It does not require a `.env` file, Docker, PostgreSQL/PostGIS, Redis, the API worker, OIDC configuration, a map style or live provider access. All data on this route are synthetic demo fixtures. Stop the server with `Ctrl+C`; optionally choose a port using `MCHO_DEMO_PORT=3001 bash scripts/start-interactive-demo.sh`. See [the local preview guide](./docs/phase-15-one-command-demo.md).

## Phase 9: operational readiness

The API now separates liveness from readiness (PostgreSQL + PostGIS + Redis), returns per-dependency failure states, and logs request IDs/status/latency without logging tokens or bodies. The admin console includes source run/checkpoint timestamps. See [operations guide](./docs/phase-9-operations.md), [backup/restore](./docs/runbooks/backup-restore.md) and [incident response](./docs/runbooks/incident-response.md). Backup policies and alert routing still require environment-level configuration and drills.

## Phase 8: admin source registry and manual ingestion

The admin-only panel provides source registration, terms/retention updates, terms approval, activation/deactivation, manual ReliefWeb run queueing, and run summaries. It displays API-side provider setup status without exposing the app-name value. Hosted ReliefWeb configuration requires matching `RELIEFWEB_APPNAME` and `RELIEFWEB_COUNTRIES` in both API and worker services; feeds remain disabled by default. See [the source-admin runbook](./docs/phase-8-source-admin.md).

## Phase 6: reviewer queue and separate publication

The `/analyst` workspace now includes the OIDC-protected review queue. Reviewers/admins can record a reasoned decision on source documents or event claims. Publishers/admins can use a separate publish action on eligible completed event tasks; the API always re-checks evidence and high-impact rules. See [review queue API details](./docs/api.md).

## Phase 5: human-authored event drafts

The API now allows an analyst/reviewer/admin to create an unpublished event draft from an individually approved source document. It records the report as a claim, links the document as evidence, creates revision 1 and a review task, and leaves verification/publication separate. See [the analyst workflow](./docs/phase-5-analyst-workflow.md). The `/analyst` browser workspace uses server-side OIDC Authorization Code + PKCE; the browser never receives the API bearer token. It supports source-document inspection, role-gated draft creation, reviewer decisions and a separate publisher action. The identity provider and matching API trust settings must be configured before sign-in works.

## Phase 4: metadata-only source ingestion

The repository includes a **manual, disabled-by-default ReliefWeb API v2 adapter**. It stores source metadata and canonical links—not article bodies. An ingestion run creates a source-document review task; it does not create or publish event claims.

See [the ingestion workflow](./docs/phase-4-ingestion.md) and [OIDC setup](./docs/security-oidc.md). A ReliefWeb source needs an admin-reviewed terms URL, retention policy, approved use status and explicit activation before an administrator can queue a run. The provider app name and country scope must also be configured in the worker. No provider is activated by default.

## Quick start

1. Copy `.env.example` to `.env` and set a strong local `POSTGRES_PASSWORD`. Configure `OIDC_*` variables only when you have an OIDC provider and access-token settings ready; reviewer endpoints fail closed otherwise.
2. Start services: `docker compose up --build -d db redis`.
3. Run migrations: `docker compose run --rm api alembic upgrade head`.
4. Start application services: `docker compose up --build api worker web`.

The Compose configuration builds the database URL from separate connection fields, safely encoding special characters in passwords. For running the API directly on your host, set `POSTGRES_HOST=localhost` and ensure a local PostGIS instance is running.
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

## Authentication

Reviewer and publisher APIs validate signed OIDC/JWT access tokens, including issuer, audience, expiration, signing key and configured roles. See [OIDC authentication setup](./docs/security-oidc.md). The Render Blueprint does not guess an identity provider; configure its trusted issuer, API audience, JWKS URL and role claim before enabling review operations.

## Phase 12: database-backed publication tests

CI now exercises a full HTTP/API flow against PostgreSQL/PostGIS: editor self-review is blocked; review alone does not publish; a different reviewer cannot publish their own decision; an independent publisher can publish only after approval; and a new revision invalidates an older approval. Test rows roll back inside an outer transaction. See [the integration-test guide](./docs/phase-12-database-integration.md).

## Phase 11: independent review and publication

The API requires a separate editor, reviewer and publisher for the exact revision being published. Publication additionally requires a positive review decision recorded after the latest immutable revision and no open review tasks. Corrections reset verification and reopen review, and cannot self-assert a verified state. See [independent publication controls](./docs/phase-11-independent-publication.md).

## Phase 10: browser-session hardening

The analyst sign-in flow uses an HttpOnly, same-origin session cookie rather than exposing access tokens to browser JavaScript. The Next.js server performs the code exchange, verifies the ID token, and injects the access token only when proxying to the API. State-changing requests are checked for same-origin Origin headers. See [BFF session hardening](./docs/phase-10-bff-session.md).

## Deployment

After a staging deployment, run [`scripts/smoke-test.sh`](./scripts/smoke-test.sh) with `API_URL` and `WEB_URL` set to the host URLs. See [the deployment guide](./docs/deploy-render.md) for provisioning, OIDC and verification steps.

A Render pilot deployment Blueprint is available in [`render.yaml`](./render.yaml). Read [the Render deployment guide](./docs/deploy-render.md) before applying it. Applying the Blueprint creates cloud resources that may incur recurring charges. No services are deployed automatically by this repository commit.

## Environment variables

See `.env.example`. Keep credentials out of source control. External provider integrations are intentionally unconfigured by default.

## Important limitations

This is an initial implementation scaffold, not a validated production intelligence system. GitHub Actions validates API/PostGIS migrations and contract tests, no-network ingestion tests, frontend typecheck/build, and API/worker/web Docker image builds. A live hosting environment and a real identity/provider configuration have not been provisioned. Before operational use, complete provider-specific licensing checks, source connectors, identity-provider integration, security review, restore testing, geospatial performance tests, satellite validation, and maritime aggregation validation. Do not use it for targeting or tactical military decisions.
