# Architecture

The MVP is a modular monolith API with a separate Celery worker process. PostgreSQL/PostGIS is the structured source of truth; object storage is reserved for raw documents and raster assets. The web app consumes versioned REST/GeoJSON APIs.

## Trust boundaries

- Public API: published, non-synthetic events and approved aggregates only.
- Reviewer/publisher API: protected by JWT access-token verification against an explicitly configured OIDC issuer, audience and JWKS endpoint. Role claims are mapped to reviewer/publisher/admin permissions. Without configuration, privileged endpoints return 503; invalid tokens return 401 and insufficient roles return 403.
- Worker: provider credentials only in its runtime environment; connector calls are disabled until configured.
- Object storage: private by default; public access only through deliberate publication controls.

## Decisions

1. Use PostGIS for indexed spatial filtering and GeoJSON conversion.
2. Store evidence separately from event claims and keep corrections in event revisions.
3. Keep maritime API aggregate-only.
4. Do not return synthetic fixtures through public event endpoints.
5. Treat provider integration as disabled unless credentials and licensing are configured.
