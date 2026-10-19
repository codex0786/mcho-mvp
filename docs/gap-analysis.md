# Gap analysis

Scope: everything on branch `phase-17-reproducible-migrations` (main `9d266d8`
plus PR #5), read in full for the API routers, worker pipeline, BFF proxy and
web screens, and probed at runtime (API on a host without a database, web dev
server, live Vercel deployment). Companion to
[current-state-assessment.md](./current-state-assessment.md); the plan that
acts on these gaps is [implementation-roadmap.md](./implementation-roadmap.md).

## Bottom line

The **governance core is strong**: source-terms gating, per-document review,
a three-person editor/reviewer/publisher chain, evidence invalidation on
source changes, and a hardened BFF session. What is missing is everything that
core is supposed to govern:

1. **Almost no data can enter the system.** One adapter (ReliefWeb metadata), manual only, never run live. Satellite, maritime and humanitarian tables have no write path at all.
2. **The evidence model stops at one document per event.** No corroboration, no conflicting evidence, no confidence components, no public revision history.
3. **The product people see is the demo.** The six-module UX in `/demo` is hard-coded fixtures; the real app has a map that needs configuration, and an analyst console.
4. **Nothing runs outside a laptop or CI.** No hosted API, database, identity provider or schedule.

Below, each gap has a severity (H/M/L) and the plan item that closes it.

## A. Correctness and integrity defects (fix first; no external dependencies)

| # | Gap | Where | Sev | Plan |
|---|---|---|---|---|
| A1 | A correction's revision snapshot is taken **before** the edit is applied, so revision N+1 stores the old content. Revision 1 stores the created state. The latest revision never matches what gets published, which breaks "traceable provenance". | `services/api/app/routers/events.py:256` vs `:275` | H | M0 |
| A2 | If a worker dies mid-run (`acks_late` redelivery), the run stays `running` and the retry returns `already_running`. The partial unique index then blocks **every future run for that source**. There is no stale-run timeout or reaper. | `services/workers/mcho_workers/ingestion.py:136` | H | M0 |
| A3 | Review decisions have no row lock. Two reviewers acting at once can both pass the "task still open" check and record conflicting decisions. | `services/api/app/routers/reviews.py:79` | M | M0 |
| A4 | Every `httpx.HTTPError` is retried 5× as transient, including 401/403/404 from a bad app name or a revoked key. | `services/workers/mcho_workers/celery_app.py:29` | M | M0 |
| A5 | Unhandled errors (e.g. database down) return a plain-text `Internal Server Error` with no JSON body and no `X-Request-ID`, because the middleware re-raises before adding the header. Verified at runtime. | `services/api/app/main.py:47` | M | M0 |
| A6 | The "source is eligible" rule is copy-pasted in six places: draft creation, publish, review invalidation, sources list/invalidate, ingestion queue, worker. One edit that misses a copy creates a publication loophole. | `routers/events.py`, `reviews.py`, `sources.py`, `ingestion.py`, `workers/ingestion.py` | M | M0 |
| A7 | `/map/events` silently truncates at 2,000 features. The client cannot tell an incomplete map from a complete one. | `routers/events.py:228` | M | M0 |

## B. Evidence and provenance model

| # | Gap | Sev | Plan |
|---|---|---|---|
| B1 | An event gets exactly one evidence link, at draft creation. There is no endpoint to attach more, so corroboration is impossible and `relationship` is always `supports`. | H | M1 |
| B2 | Conflicting or contradicting evidence cannot be recorded, so disputes cannot be shown side by side. | H | M1 |
| B3 | Corrections can change only `summary`. Type, time, location, uncertainty and country cannot be corrected without bypassing the workflow. | H | M1 |
| B4 | The public API exposes neither revision/correction history nor review outcome; `/events/{id}/evidence` omits document review status. | M | M1 |
| B5 | `confidence_label` is a free string that nothing sets; every event is `unassessed`. There are no component scores and no methodology. | M | M1 |
| B6 | No publisher "withdraw" action. Only a reviewer's `reject` withdraws, which mixes two roles. | M | M1 |
| B7 | `claims` rows are written but never read; `alerts` is never used. | L | M1 (use or drop) |
| B8 | No duplicate detection between events, so two analysts can draft the same incident twice. | M | M5 |

## C. Data acquisition

| # | Gap | Sev | Plan |
|---|---|---|---|
| C1 | ReliefWeb is the only adapter. It runs only when an admin clicks, and has never run against the real API (needs an approved app name). | H | M3 |
| C2 | No scheduler (no Celery beat), freshness SLA or stale-source alert. | H | M3 |
| C3 | Satellite, maritime and humanitarian tables have **no write path**: no adapter, admin form or import. The `copernicus`/`nasa_firms`/`maritime_feed` connectors only check env vars. | H | M4 |
| C4 | Observation tables lack provenance (except humanitarian's optional document link), `is_synthetic` and publication status. PR #5 locks them to staff as an interim measure. | H | M4 |
| C5 | `retention_policy` is free text and nothing enforces it. | M | M5 |

## D. Product and frontend

| # | Gap | Sev | Plan |
|---|---|---|---|
| D1 | The six-module experience (overview, explorer, satellite, humanitarian, maritime, methodology) exists only in `/demo` as fixtures and shares no components with the real app. | H | M2 |
| D2 | No real-data event list, event detail or evidence panel page. The home page's sidebar is filled by imperative DOM writes (`document.getElementById`) from inside the map component. | H | M2 |
| D3 | The home map needs a MapLibre style URL and shows nothing without one, so the live Vercel home page is effectively empty. | M | M2 |
| D4 | No search, saved filters, export or reports. | M | M5 |
| D5 | Analyst sessions hard-expire after at most one hour with no refresh, and sign-out doesn't end the identity-provider session. | M | M3 |
| D6 | No audit-log view; the admin panel only knows ReliefWeb. | M | M5 |
| D7 | No CSP, frame-ancestors, referrer or content-type headers. Verified locally and on Vercel, which adds only HSTS. | M | M0 |
| D8 | No committed npm lockfile, so CI, Docker and Vercel resolve versions independently. | M | M0 |

## E. Platform and operations

| # | Gap | Sev | Plan |
|---|---|---|---|
| E1 | No hosted API, worker, PostGIS or Redis. `render.yaml` has never been applied. | H | M3 (owner decision) |
| E2 | No identity provider, so `/analyst` cannot be used anywhere. | H | M3 (owner decision) |
| E3 | No rate limiting or request-size limits on the API. | M | M5 |
| E4 | No metrics or alerting beyond JSON request logs; no DB statement timeout. | M | M5 |
| E5 | Backup/restore never drilled; Compose stack not verified end-to-end. | M | M3 |

## What is already good (keep it)

- Fail-closed auth everywhere (503 when unconfigured, 401/403 otherwise), with OIDC hardening and a BFF that never exposes tokens.
- Publication is gated on evidence plus terms plus independent review, and source or document changes automatically unpublish.
- The ingestion design: checkpoints, overlap windows, content-hash dedup, a sanitised error ledger, and no article bodies stored.
- Honest labelling: the demo banner, the "no live feed" notices, synthetic records excluded from public APIs.
- The test culture: DB-backed workflow tests, Playwright, and drift checks in CI (PR #5).
