# Phase 9 — Runtime observability and operational readiness

## Implemented

### API service probes

- `GET /api/v1/health/live` reports whether the process responds. It intentionally does not depend on PostgreSQL or Redis so an orchestrator does not restart a healthy process only because a downstream dependency is recovering.
- `GET /api/v1/health/ready` tests PostgreSQL, the PostGIS extension and Redis/queue connectivity independently. It returns HTTP 200 only when all three are reachable, or HTTP 503 with per-dependency status. Error details are sanitized.
- Liveness and readiness are separate; deploy platforms should use liveness for basic process checks and readiness for user-serving dependency checks.

### Request logs and correlation

The API logs a JSON-formatted request record containing event type, request ID, method, route path, status code and duration in milliseconds. Exceptions log only the exception type, not its message or stack payload. A validated `X-Request-ID` is propagated or replaced with a UUID and returned to the caller. Query strings, request bodies, bearer tokens and cookies are not logged.

The same-origin web proxy forwards the correlation header if present, strips cookies and avoids caching API responses. The public web runtime configuration endpoint returns configuration keys only—never secrets.

### Admin operational snapshot

`GET /api/v1/ingestion/operations` is admin-only and provides:
- source counts (total, active, terms-review required, provider config missing, never ingested);
- active-run count and runs created in the last 24 hours grouped by status;
- per-source operational state, latest run state/timestamps, checkpoint age, and provider watermark when available.

The admin source panel displays the snapshot next to manual run history. Values are explicitly operational metadata: they do not verify event truth, prove provider connectivity, or make any inference from an empty queue/checkpoint.

## Validate a staging deployment

Run:

```bash
API_URL="https://<mcho-api-host>" WEB_URL="https://<mcho-web-host>" ./scripts/smoke-test.sh
```

The script checks API liveness/readiness, JSON contracts for published events and the GeoJSON map, homepage availability, public runtime configuration and the same-origin backend proxy. It confirms wiring only—not source licensing, data accuracy, or operational suitability.

## Still required before production

- Alert routing and thresholds for API availability/latency, dependency readiness, worker heartbeat, queued/running run age, failed/partial run rates, checkpoint age and review-queue age.
- A durable log sink, retention/access policy and notification/on-call ownership.
- Database backup retention, recovery objectives and a successful isolated restore test.
- Load/security tests, dependency/image scanning policy, secret rotation, and documented incident ownership.
- Provider-specific uptime/rate-limit/freshness monitoring after source terms have been reviewed and connectors enabled.
