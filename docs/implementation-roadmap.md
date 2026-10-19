# Implementation roadmap and backlog

Companion to [current-state-assessment.md](./current-state-assessment.md). The
earlier "Phase N" docs record what was built; this file orders what comes next.
Complexity: S ≈ under a day, M ≈ 1–3 days, L ≈ a week or more.

## Sequencing

1. **Stabilise (now):** reproducible installs and migrations, trust-boundary fixes, a verified local full stack.
2. **Hosted pilot (needs owner decision):** API + PostGIS + Redis + OIDC in one staging environment; live smoke tests.
3. **Evidence depth:** confidence components, observation publication model, audit read API.
4. **Sources:** one real adapter per family, each only after its licence review.
5. **Analyst outputs:** search, saved views, CSV export with dataset version.
6. **Production hardening:** rate limits, headers, metrics/alerts, backup drill, security review.

## Backlog

| ID | Item | Severity | Size | Depends on | Acceptance criteria |
|---|---|---|---|---|---|
| B-01 | Explicit migrations + drift check | High | M | — | **Done on `phase-17-reproducible-migrations`, pending CI.** Fresh DB `upgrade head` → `alembic check` clean; `downgrade base` → `upgrade head` clean. |
| B-02 | Gate observation endpoints | High | S | — | **Done on the same branch.** Anonymous → 503/401, non-staff role → 403 (tests). |
| B-03 | Commit `apps/web/package-lock.json`; switch CI and Dockerfile to `npm ci` | High | S | — | Two clean installs resolve identical versions; CI uses the lockfile. |
| B-04 | Verify the Compose stack end-to-end | High | S | Docker | `scripts/start-local-stack.sh` passes its smoke tests on a clean checkout; result recorded. |
| B-05 | Publication model for observations | High | L | B-01 | Imagery/maritime/humanitarian rows carry `source_document_id`/provenance, `is_synthetic`, review + publication status; public endpoints return only published, non-synthetic rows; then B-02's restriction can be relaxed for published rows. |
| B-06 | Staging deployment (API, worker, PostGIS, Redis) | High | M | Owner approval of host + cost | `/health/ready` OK in staging; migrations applied by the pre-deploy step; `scripts/smoke-test.sh` passes against live URLs. |
| B-07 | OIDC provider integration in staging | High | M | B-06, provider choice | Real sign-in to `/analyst`; analyst/reviewer/publisher roles mapped; a full draft→review→publish run done by three distinct accounts. |
| B-08 | API rate limits and request-size limits | Medium | S | — | Excess requests return 429; oversized bodies rejected; tests. |
| B-09 | Web security headers (CSP, frame-ancestors, referrer, HSTS in prod) | Medium | S | — | Headers present on all routes; `/demo` and `/analyst` still pass Playwright. |
| B-10 | Confidence components (source reliability, corroboration, spatial/temporal precision) with versioned rules | Medium | L | — | Each component stored and explained; review status stays separate; scoring tests on representative cases. |
| B-11 | Audit-log read API + admin view | Medium | M | — | Admins can filter audit entries by subject; non-admins get 403. |
| B-12 | Scheduled ingestion (Celery beat) + freshness alert | Medium | M | B-06 | Schedule per active source; stale source surfaces in `/ingestion/operations`; failed run can be replayed. |
| B-13 | ReliefWeb live verification | Medium | S | Approved app name, terms review | One real run recorded with counts; only then label the source as live. |
| B-14 | Humanitarian indicator adapter (e.g. HDX HAPI) | Medium | L | Licence review, B-05 | Units, geography, period, source and caveats stored; missing ≠ zero; fixture tests. |
| B-15 | Satellite scene metadata adapter (Copernicus) | Medium | L | Account, B-05 | Scene metadata (sensor, time, cloud cover, footprint) ingested; footprint has a GiST index; no damage claims. |
| B-16 | Maritime aggregates | Low | L | Licensed provider, risk assessment, B-05 | Aggregates only, coarsened and delayed per assessment; no vessel-level data in API or exports. |
| B-17 | Event search, saved filters, CSV export with filter + dataset version | Low | L | B-06 | Export matches filters; CSV escaping tested; export records its parameters. |
| B-18 | Housekeeping: delete squash-merged phase branches; refresh `IMPLEMENTATION_STATUS.md` | Low | S | Owner confirmation | Only active branches remain; status file matches CI. |

## Explicitly not planned without a new decision
- Automated event creation or publication from source text.
- Real-time or vessel-level maritime tracking.
- Any paid infrastructure, domain purchase or provider account creation.
