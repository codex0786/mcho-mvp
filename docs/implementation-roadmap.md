# Implementation plan

Acts on [gap-analysis.md](./gap-analysis.md) (gap IDs like A1, B3 refer to it).
Size: S under a day, M 1–3 days, L about a week. "Blocked" means it needs a
decision, account or approval from the project owner; everything else can
start now.

## Principles for ordering

1. Fix integrity defects before building on them (M0).
2. Complete the evidence model before adding data volume, because every new source inherits it (M1).
3. Build the real UI against the API with mocked responses so it doesn't wait on hosting (M2 runs in parallel with M3).
4. Add a data family only after its licence review, and ship it behind the same review/publication gates as events (M4).
5. No paid infrastructure, accounts or domains without explicit approval.

## M0 — Integrity fixes (≈1 week, no blockers)

Status: implemented on branch `phase-19-m0-integrity`; see that branch's CI run for verification.

| Item | Closes | Size | Acceptance criteria |
|---|---|---|---|
| Correction stores the **post-edit** snapshot; revision 1..N always equals the event state at that revision | A1 | S | DB test: correct → latest revision snapshot equals current event fields |
| Stale-run reaper: `running` older than a timeout → `failed` with a reason; `started_at` heartbeat | A2 | M | Test: a run stuck in `running` past the timeout no longer blocks a new run |
| `SELECT … FOR UPDATE` on the review task in `decide` | A3 | S | Concurrent-decision test: exactly one succeeds, one gets 409 |
| Retry only timeouts, connection errors, 429 and 5xx; fail fast on other 4xx | A4 | S | Connector tests for 403 (no retry) and 503 (retry) |
| Global exception handler returning `{"detail", "request_id"}` JSON with the `X-Request-ID` header | A5 | S | Test with a failing DB dependency: 500 JSON plus request ID |
| One `source_is_publishable()` used by all six call sites | A6 | S | Grep shows a single definition; existing tests stay green |
| `/map/events` returns `truncated: true` and the limit; UI shows "showing first N" | A7 | S | Contract test |
| Commit `apps/web/package-lock.json`; `npm ci` in CI and Dockerfile | D8 | S | CI uses the lockfile |
| Security headers via `next.config.ts` (CSP, frame-ancestors, referrer, nosniff) | D7 | S | Headers present; Playwright still green |

## M1 — Evidence model completion (≈2–3 weeks, no blockers)

| Item | Closes | Size | Acceptance criteria |
|---|---|---|---|
| `POST /events/{id}/evidence`: link more approved documents as `supports`, `contradicts` or `context`; creates a revision and reopens review | B1, B2 | M | A link to an unapproved document is rejected; the event returns to review; audit entry written |
| Full correction payload (type, times, location, uncertainty, country) with the same validators as drafts | B3 | M | Every field correctable; each correction is a new revision; review reopens |
| Publisher `POST /events/{id}/withdraw` with a reason | B6 | S | Only publisher/admin; audited; event leaves the public API |
| Public `/events/{id}/history` (revisions, review outcomes without reviewer identity) and an evidence response that includes document review status and relationship | B4 | M | Unpublished/synthetic events stay 404; no reviewer PII exposed |
| Confidence v1: stored components (source reliability, corroboration count, spatial precision, temporal precision) plus a versioned rule set and a written methodology; review status kept separate | B5 | L | Each component explained in the API; scoring tests on representative cases; `docs/methodology/confidence.md` |
| Use `claims` (claim per evidence link) or drop the table; decide on `alerts` | B7 | S | No unused tables remain |

## M2 — Real-data product UI (≈3 weeks, parallel with M3)

| Item | Closes | Size | Acceptance criteria |
|---|---|---|---|
| Shared component library extracted from `/demo` (nav, panels, status badges, empty/error/loading states) | D1 | M | `/demo` rebuilt on it with no visual regressions (Playwright) |
| Event explorer page on `GET /events` (filters: date, country, type, verification) with URL-encoded filter state | D1, D2 | M | Filters round-trip through the URL; Playwright tests against intercepted API responses |
| Event detail page with an evidence panel (supports/contradicts, timestamps, review status, confidence explanation, history) | D2, B4 | M | Shows conflicting evidence side by side; stale and disputed states visibly labelled |
| Rewrite the home map as a controlled React component (no `getElementById`), with a permitted no-key basemap or an explicit "no basemap" layer | D2, D3 | M | Works with no style URL configured; truncation notice shown |
| Clear mode labelling across the app: synthetic, pending review, disputed, stale, published | D1 | S | Each state has a test fixture and a visual label |

## M3 — Hosted staging and live data (≈2 weeks once unblocked) — **Blocked**

Owner decisions needed first: hosting provider and monthly budget, identity
provider, basemap provider, ReliefWeb app-name application.

| Item | Closes | Size | Acceptance criteria |
|---|---|---|---|
| Staging API, PostGIS and Redis on free tiers (Render + Neon + Upstash, `render.yaml`, [guide](./deploy-free-tier.md)); worker deferred until a free or approved paid option exists | E1 | M | `/health/ready` OK; migrations applied at start; `scripts/smoke-test.sh` passes against live URLs |
| OIDC tenant with analyst/reviewer/publisher/admin roles; refresh-token or silent re-auth; IdP logout | E2, D5 | M | Three distinct accounts complete draft → review → publish in staging |
| ReliefWeb live verification, then Celery beat schedule per active source and a freshness alert in `/ingestion/operations` | C1, C2 | M | One real run recorded with counts; a stale source is flagged; a failed run can be replayed |
| Compose stack verified end-to-end; first backup/restore drill | E5 | S | Drill result recorded in the runbook |

## M4 — Observation families (≈4–6 weeks, each blocked on its licence review)

| Item | Closes | Size | Acceptance criteria |
|---|---|---|---|
| Observation publication model: `source_document_id`, `is_synthetic`, review and publication status on all three tables; public endpoints serve only published rows; relax PR #5's staff-only gate for those rows | C4 | M | Migration plus tests; unpublished rows invisible publicly |
| Humanitarian indicators adapter (first; lowest risk), e.g. HDX HAPI after a terms review | C3 | L | Units, geography, period, source and caveats stored; missing ≠ 0; fixture tests; explorer charts in M2 style |
| Satellite scene **metadata** adapter (e.g. Copernicus catalogue): sensor, time, cloud cover, footprint with GiST index | C3 | L | No damage claims; observation kept separate from interpretation |
| Maritime aggregates, **only** with a licensed provider and a written risk assessment: coarsened, delayed, aggregate-only | C3 | L | No vessel-level data in API, map or export; anomaly flags carry their baseline |

## M5 — Analyst outputs and production hardening (≈3–4 weeks)

| Item | Closes | Size | Acceptance criteria |
|---|---|---|---|
| Search, saved filters, CSV export recording filters and dataset version | D4 | L | Export matches filters; CSV escaping tested |
| Audit-log API and admin view; generic source admin (beyond ReliefWeb) | D6 | M | Admin-only; filterable by subject |
| Duplicate-candidate detection between events (flag only, never auto-merge) | B8 | M | Candidates shown to reviewers with the matching signals |
| Retention enforcement job per source policy | C5 | M | Expired raw metadata pruned; derived records keep references |
| Rate limits, body-size limits, DB statement timeout | E3, E4 | S | 429 and 413 tests |
| Metrics (latency, errors, queue depth, freshness) and alert routing | E4 | M | A dashboard plus at least one alert verified firing |
| External security review and source-licensing review before any public launch | — | — | Findings tracked to closure |

## Decisions the owner needs to make

1. Merge PR #5 (reproducible migrations, observation gate).
2. Hosting provider and budget for staging (M3).
3. Identity provider (M3).
4. Basemap provider, or accept a no-basemap map (M2).
5. Apply for a ReliefWeb app name and approve its terms (M3).
6. Which humanitarian source to integrate first (M4).

## Explicitly out of scope without a new decision

- Automated event creation or publication from source text.
- Real-time or vessel-level maritime tracking.
- Any paid infrastructure, domain purchase or provider account creation.
