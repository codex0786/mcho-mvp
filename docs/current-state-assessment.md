# Current-state assessment

Assessed commit: `9d266d8` on `main` (2026-10-19), plus the changes on branch
`phase-17-reproducible-migrations` described at the end. Deployment checked:
<https://mcho-mvp.vercel.app>.

This is an evidence statement, not a readiness claim. "Verified" below means a
test or live check was run during this assessment and passed.

## Verification performed

| Check | Where | Result |
|---|---|---|
| API unit/contract tests (`pytest`) | local, Python 3.12 | 30 passed, 2 skipped (PostGIS integration tests need `MCHO_INTEGRATION_TESTS=1` + DB) |
| Worker connector tests | local | 6 passed |
| Web OIDC BFF tests (`npm run test:auth`) | local, Node 26 | 4 passed |
| Web typecheck + production build | local | pass |
| Playwright `/demo` acceptance | local, Chromium | 7 passed |
| Full CI incl. PostGIS migrations and DB-backed publication tests | GitHub Actions on `9d266d8` | success |
| Live routes `/`, `/demo`, `/analyst`, `/api/public-config` | Vercel | all HTTP 200; public config is empty (no OIDC, no map style) |
| Docker Compose full stack | — | **not run**: no Docker daemon on the assessment machine; CI only validates `compose config` and image builds |

## Status by area

### 1. Implemented and verified
- `/demo`: self-contained prototype, synthetic fixtures, zero network calls, clear synthetic labelling, mobile layout. Live on Vercel.
- Event publication workflow: three-person editor/reviewer/publisher independence, post-revision review requirement, evidence + source-terms gates, corrections reopen review (DB-backed CI tests).
- OIDC access-token verification (issuer/audience/JWKS/alg allowlist), role guards, fail-closed 503 when unconfigured (unit tests).
- Web BFF: server-side code exchange, HttpOnly cookie, same-origin mutation checks (unit tests).
- Public event/map APIs exclude unpublished and synthetic records (tests).
- ReliefWeb metadata connector normalisation and dedup logic (no-network fixture tests).

### 2. Implemented but not verified end-to-end
- Docker Compose stack and `scripts/start-local-stack.sh` (images build in CI; the stack was not started here).
- ReliefWeb ingestion against the real API (blocked: needs an approved app name; see §5).
- Analyst workspace (`/analyst`) against a real identity provider.
- Liveness/readiness probes against real Redis/PostGIS outside CI.
- Backup/restore and incident runbooks (documented, never drilled).

### 3. Partially implemented
- **Satellite, maritime, humanitarian**: tables and read endpoints exist, but nothing writes to them, and they have no review/publication status, provenance link (except humanitarian's optional `source_document_id`) or synthetic flag.
- **Ingestion framework**: run ledger, checkpoints, retries, dedup and error ledger exist; scheduling (Celery beat), freshness alerting and replay UI do not.
- **Home page `/`**: real map/API client, but on Vercel there is no API, no map style and no OIDC, so it shows only configuration-needed states.
- **Confidence**: `confidence_label` is a free string defaulting to `unassessed`; no component scores or methodology.
- **Audit log**: written for review/publication/source actions; no read API or UI.

### 4. Missing
- Event normalisation from source records into events (by design, drafts are human-authored only), entity resolution, similarity-based dedup.
- Confidence/quality scoring framework, saved views, exports/reports, global search.
- Satellite scene ingestion (Copernicus), NASA FIRMS, HDX/humanitarian adapters, licensed maritime aggregation — the connector files are configuration guards only.
- Rate limiting and request-size limits on the API; security headers on the web app.
- Committed npm lockfile (builds resolve dependency versions at install time).
- Metrics/alerting beyond structured request logs.

### 5. Blocked by external dependencies
| Blocker | Needs |
|---|---|
| Hosted API, worker, PostGIS, Redis | A hosting decision and billing approval (`render.yaml` exists but has never been applied) |
| Analyst sign-in | An OIDC provider tenant, client registration, role mapping |
| ReliefWeb live ingestion | Approved ReliefWeb app name, terms review, country scope |
| Copernicus / FIRMS / maritime | Accounts, keys and licence review; maritime additionally needs a risk assessment |
| Basemap on `/` | A permitted MapLibre style URL |

## Frontend → backend map

| Screen | Data source | Works without backend? |
|---|---|---|
| `/demo` | In-file synthetic fixtures | Yes |
| `/` | `GET /map/events` via `/api/backend` proxy; `/api/public-config` | Renders, but shows "not configured"/"unavailable" states |
| `/analyst` | `/auth/*`, `/sources`, `/sources/admin`, `/ingestion/*`, `/reviews/tasks*`, `/events/drafts/*`, `/events/{id}/publish` | No — requires OIDC and API |

Observation endpoints (`/imagery/scenes`, `/maritime/aggregates`, `/humanitarian/indicators`) are not called by any screen.

## Top three blockers to a reliable working application

1. **Non-reproducible schema migrations** (severity: high). `0001_initial` ran `Base.metadata.create_all` against the *current* models, and `0002` did the same for its tables. A fresh database therefore got whatever the code looked like at install time, every future column change would collide with it, and CI could not detect model/migration drift. → **Fixed on this branch** (see below).
2. **Observation endpoints broke the documented public trust boundary** (severity: high, safety). `docs/architecture.md` says the public API serves "approved aggregates only", but imagery, maritime and humanitarian rows were readable anonymously with no review status, publication gate or synthetic flag — any row an operator inserted would be public immediately, including maritime data. → **Fixed on this branch** by restricting them to staff roles until a publication model exists (plan M4, gap C4).
3. **No hosted backend** (severity: high, blocked). Only the Next.js app is deployed; `/` and `/analyst` cannot function in production until the API, PostGIS, Redis and an OIDC provider are provisioned. Needs an infrastructure and billing decision from the project owner; not something code changes can resolve.

## Changes made on `phase-17-reproducible-migrations`

- `0001_initial` and `0002_ingestion_framework` now contain explicit, frozen `op.create_table` DDL. `0002` still creates its tables only when absent, so databases bootstrapped by the legacy `0001` continue to upgrade. Downgrades drop the enum types too.
- `alembic/env.py` ignores PostGIS-owned tables (`spatial_ref_sys`) during comparison.
- CI now runs `alembic check` after upgrade and a `downgrade base → upgrade head → check` round trip.
- Observation endpoints require an analyst, reviewer, publisher or admin role; 6 new tests cover the fail-closed (503) and wrong-role (403) cases.
- `.gitignore` covers `*.egg-info`, Playwright output and `*.tsbuildinfo`.

## Housekeeping notes
- Remote branches `phase-13` … `phase-16` were squash-merged: `git diff main origin/<branch>` shows only content that `main` already has (phase-16 is identical). They can be deleted once the owner confirms.
- `IMPLEMENTATION_STATUS.md` still says Phase 12 CI "must pass"; it has since passed on `9d266d8`.
