# API overview

OpenAPI docs are served at `/docs`.

- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`
- `GET /api/v1/sources`
- `GET /api/v1/events`
- `POST /api/v1/events/drafts/from-document/{document_id}` (analyst/reviewer/admin OIDC role; source document must be individually approved and its source active with reviewed terms)
- `GET /api/v1/events/{event_id}`
- `GET /api/v1/events/{event_id}/evidence`
- `GET /api/v1/map/events?west=...&south=...&east=...&north=...`
- `GET /api/v1/imagery/scenes`
- `GET /api/v1/maritime/aggregates`
- `GET /api/v1/humanitarian/indicators`
- `GET /api/v1/reviews/tasks` (reviewer/publisher/admin OIDC role)
- `POST /api/v1/reviews/tasks/{task_id}/decisions` (reviewer/admin OIDC role)
- `POST /api/v1/events/{event_id}/corrections` (publisher/admin OIDC role)
- `POST /api/v1/events/{event_id}/publish` (publisher/admin OIDC role; requires reviewed linked evidence and eligible verification status)

Event listing only returns published, non-synthetic records. Map queries require a bounding box and use PostGIS. The v1 bounding-box endpoint does not support antimeridian-crossing boxes.


## Analyst drafting workflow

Source reports are metadata-only records and are not automatically treated as facts. An analyst can create a human-authored event draft from an individually approved source document. The API records a reported-claim row, evidence link, initial revision, review task and audit event; it returns an unpublished `pending_review` event. Verification and publication remain separate human actions. Draft coordinates require an explicit uncertainty estimate; timestamps must include an offset.
