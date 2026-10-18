# API overview

OpenAPI docs are served at `/docs`.

- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`
- `GET /api/v1/sources`
- `GET /api/v1/events`
- `GET /api/v1/events/{event_id}`
- `GET /api/v1/events/{event_id}/evidence`
- `GET /api/v1/map/events?west=...&south=...&east=...&north=...`
- `GET /api/v1/imagery/scenes`
- `GET /api/v1/maritime/aggregates`
- `GET /api/v1/humanitarian/indicators`
- `GET /api/v1/reviews/tasks` (reviewer key required)
- `POST /api/v1/reviews/tasks/{task_id}/decisions` (reviewer key required)
- `POST /api/v1/events/{event_id}/corrections` (reviewer key required)
- `POST /api/v1/events/{event_id}/publish` (reviewer key required; requires linked evidence and eligible verification status)

Event listing only returns published, non-synthetic records. Map queries require a bounding box and use PostGIS. The v1 bounding-box endpoint does not support antimeridian-crossing boxes.
