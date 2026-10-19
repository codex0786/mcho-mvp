# API overview

OpenAPI docs are served at `/docs`.

- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`
- `GET /api/v1/auth/me` (verified OIDC access token; returns subject/issuer/roles, never the token)
- `GET /api/v1/ingestion/configuration` (admin role; safe ReliefWeb config status, never returns the app-name value)
- `GET /api/v1/ingestion/operations` (admin role; source checkpoint/run-state summary; operational metadata only)
- `GET /api/v1/sources`
- `GET /api/v1/events`
- `POST /api/v1/events/drafts/from-document/{document_id}` (analyst/reviewer/admin OIDC role; source document must be individually approved and its source active with reviewed terms)
- `GET /api/v1/events/{event_id}`
- `GET /api/v1/events/{event_id}/evidence`
- `GET /api/v1/map/events?west=...&south=...&east=...&north=...` (returns at most `feature_limit` features; `truncated: true` means the view held more)
- `GET /api/v1/imagery/scenes` (analyst/reviewer/publisher/admin OIDC role; restricted until observations have publication and provenance gates)
- `GET /api/v1/maritime/aggregates` (analyst/reviewer/publisher/admin OIDC role; restricted until observations have publication and provenance gates)
- `GET /api/v1/humanitarian/indicators` (analyst/reviewer/publisher/admin OIDC role; restricted until observations have publication and provenance gates)
- `GET /api/v1/reviews/tasks` (reviewer/publisher/admin OIDC role)
- `POST /api/v1/reviews/tasks/{task_id}/decisions` (reviewer/admin OIDC role)
- `GET /api/v1/reviews/tasks?status=pending` (reviewer/publisher/admin OIDC role; includes subject summary and source context)
- `POST /api/v1/events/{event_id}/corrections` (publisher/admin OIDC role)
- `POST /api/v1/events/{event_id}/publish` (publisher/admin OIDC role; requires reviewed linked evidence and eligible verification status)

Event listing only returns published, non-synthetic records. Map queries require a bounding box and use PostGIS. The v1 bounding-box endpoint does not support antimeridian-crossing boxes.


## Analyst drafting workflow

Source reports are metadata-only records and are not automatically treated as facts. An analyst can create a human-authored event draft from an individually approved source document. The API records a reported-claim row, evidence link, initial revision, review task and audit event; it returns an unpublished `pending_review` event. Verification and publication remain separate human actions. Draft coordinates require an explicit uncertainty estimate; timestamps must include an offset.


The browser analyst workspace is available at `/analyst` when OIDC browser configuration has been supplied to the web service. The access token is validated again by the API and role checks remain server-enforced.


The analyst workspace includes a role-gated review queue. Reviewer/admin users can record a rationale and decide source-document/event tasks; this changes review state only. Publisher/admin users see a separate publish action only for completed event tasks with verified/provisional status. The server always rechecks the publication evidence and high-impact gates.


The admin-only source panel in `/analyst` supports source registration, review attestation, activation/deactivation, manual ingestion queueing and run summaries. The API reports configuration state without returning the app-name value; operators must also set the same app name and country scope on the worker. This is a configuration check, not an upstream connectivity check.


Readiness now requires PostgreSQL, PostGIS and Redis. Liveness is intentionally process-only. API request logs include a validated request ID, route path, HTTP status and duration but omit query strings, request bodies, cookies and authorization tokens.

## Errors

Handled errors return `{"detail": ...}` with an HTTP status. Unhandled server errors return `500` with `{"detail": "Internal server error.", "request_id": "..."}`; every response carries an `X-Request-ID` header for log correlation (a valid caller-supplied `X-Request-ID` is echoed). Exception text is never returned.
