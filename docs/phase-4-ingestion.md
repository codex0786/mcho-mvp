# Phase 4 — Evidence-preserving source ingestion

## Pipeline

1. Register source: an administrator records provider, terms URL, access mode, owner, retention policy and refresh cadence. New sources start inactive and with unreviewed use status.
2. Review permitted use: an administrator checks the actual source terms and sets an allowed status (approved, public_domain, open_license or licensed). Approval requires a terms URL; activation additionally requires a retention policy. A changed terms URL clears the previous review.
3. Queue one bounded run: an admin-only API creates a run record and audit entry before dispatch. A partial unique database index prevents multiple queued/running/retrying runs for the same source.
4. Fetch metadata: a Celery worker uses the provider adapter with timeouts, bounded page size/page count and explicit country scope. Provider configuration is runtime-only.
5. Normalize and deduplicate: provider IDs are unique per source. A stable hash over normalized metadata avoids duplicates when the same report appears in an overlap window. The raw article body is never fetched or persisted by the ReliefWeb adapter.
6. Checkpoint and report errors: the pipeline stores run metrics and a source cursor. Individual malformed rows produce a hash and sanitized error category only; the raw provider payload is not copied to the error ledger.
7. Human review: each new/changed source document receives a review task. It remains a candidate until individually approved; it is not an event and cannot satisfy an event publication gate before review.
8. Publish separately: human-authored events require evidence links. Publication checks the source's current use status and the linked document's individual review status. Removing the last qualifying evidence from a published event takes it out of public status and creates an audit entry.

## Endpoints

| Endpoint | Role | Purpose |
|---|---|---|
| POST /api/v1/sources | admin | Register an inactive source |
| PATCH /api/v1/sources/{id} | admin | Update terms/use review or activate |
| GET /api/v1/sources/admin | admin | Inspect full source registry |
| POST /api/v1/ingestion/sources/{id}/runs | admin | Queue a manual run |
| GET /api/v1/ingestion/runs | admin | Inspect runs and checkpoints |
| GET /api/v1/ingestion/runs/{id}/errors | admin | Inspect sanitized row errors |
| GET /api/v1/ingestion/documents | analyst/reviewer/publisher/admin | Browse metadata and review status |
| GET /api/v1/ingestion/documents/{id} | analyst/reviewer/publisher/admin | Inspect provenance |

## ReliefWeb configuration and bounds

The adapter requires a pre-approved RELIEFWEB_APPNAME and a non-empty RELIEFWEB_COUNTRIES list. Operational limits are bounded: page size defaults to 100 and cannot exceed 100; maximum pages defaults to 3 and cannot exceed 10; initial lookback defaults to 7 days and cannot exceed 30; overlap defaults to 24 hours and cannot exceed 72.

The request explicitly selects title, canonical URL, dates, country, source, language and format metadata; it does not request report body fields. Paging uses the provider's totalCount for whole-query count rather than the count value for one response. Date queries overlap the last committed watermark to tolerate late-arriving reports; external IDs and stable content hashes make the overlap idempotent.

## Operational guardrails

- Having connector code does not mean provider access is approved. Database source activation and environment configuration are independent gates.
- No scheduled polling is configured. Runs are manually queued by an administrator.
- The worker writes source documents, checkpoints and run metadata only; it never creates or publishes events automatically.
- Keep report content on the provider's canonical URL unless a license has explicitly been reviewed for another storage/use pattern.
- Review terms, attribution obligations, privacy considerations, rate limits and retention before activation.

## Acceptance criteria

- [ ] Fresh PostGIS install and upgrade from the previous migration pass.
- [ ] API role checks, source terms validation and publication-gate tests pass.
- [ ] No-network connector tests cover missing configuration, pagination, bounds, canonical URLs, no-body retention and stable hashes.
- [ ] Worker/API/web Docker builds and frontend production build pass.
- [ ] A staging ingestion run is possible only after an administrator completes source/provider configuration.
- [ ] Every created document has a provenance URL/hash, review status and review task.
