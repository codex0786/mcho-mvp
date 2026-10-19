# Render pilot deployment

This repository includes a Render Blueprint at `render.yaml` defining the API, frontend, Celery worker, private Key Value queue and PostgreSQL database. Render Blueprints manage connected services from YAML, and Render Postgres supports PostGIS. See the [Blueprint reference](https://render.com/docs/blueprint-spec) and [Postgres extensions](https://render.com/docs/postgresql-extensions).

## Important: costs and scope

**Review current Render pricing before applying the Blueprint.** Applying it provisions cloud services and may incur recurring charges. The initial configuration is sized for a small pilot, not a load-tested production system. Singapore co-location is the current default; review latency, data handling, provider terms and regional requirements before use.

The Blueprint is not deployed automatically by this commit. It does not provision real provider credentials, enable ingestion or configure production identity. It is infrastructure-as-code for a controlled staging deployment, not proof that the observatory is operational.

## Apply the Blueprint

1. Open Render and choose **New → Blueprint**.
2. Connect `https://github.com/codex0786/mcho-mvp` and select branch `main`.
3. Review each service, region, plan, database settings and recurring cost before confirming provisioning.
4. When prompted for `CORS_ORIGINS`, enter the exact HTTPS origin of the new `mcho-web` service, without a trailing slash (for example, `https://mcho-web.onrender.com`). Confirm the actual URL Render assigns.
5. Render builds the API, worker and frontend Dockerfiles. The API pre-deploy command applies Alembic migrations before the API becomes active; inspect its deploy logs.
6. Confirm successful deployment of `mcho-api`, `mcho-worker`, `mcho-web`, `mcho-queue` and `mcho-db`.
7. Set `NEXT_PUBLIC_MAP_STYLE_URL` for `mcho-web` to a permitted MapLibre style JSON URL if you want a basemap. The blank default is intentional.
8. Open the Render-assigned public URL for `mcho-web`.

The Blueprint wires the API origin into the frontend using Render's `RENDER_EXTERNAL_URL` environment variable. The API's CORS allowlist is entered separately to avoid a circular cross-service dependency. Render documents these fields in its [Blueprint specification](https://render.com/docs/blueprint-spec).

## Configuration and security

- Managed PostgreSQL URLs using `postgres://` or `postgresql://` are normalized to SQLAlchemy's `postgresql+psycopg://` driver format. The API Dockerfile listens on the platform-provided `PORT`.
- The Redis-compatible Key Value is configured for internal connections only. Keep queue access private.
- `NEXT_PUBLIC_*` settings are browser-visible configuration; never put secrets in them.
- OIDC issuer, API audience, JWKS URL and role claim are intentionally not set in the Blueprint because the organization must choose/configure its identity provider. Set them in the `mcho-api` service environment after configuring the provider; until then, reviewer endpoints return 503.
- A ReliefWeb metadata connector is included but remains disabled until a pre-approved RELIEFWEB_APPNAME, explicit RELIEFWEB_COUNTRIES, an active source with reviewed terms/retention policy and human-review workflow are configured. It fetches metadata and links only. HDX HAPI, Copernicus, NASA FIRMS and maritime aggregation are not enabled. Never describe the site as live-data enabled until provider terms, QA and freshness monitoring pass.
- Put real provider credentials only in the hosting dashboard's secret environment settings after checking source terms and least-privilege requirements.

## Smoke tests after deployment

Let `API_URL` be the public `mcho-api` URL without a trailing slash:

- `GET $API_URL/api/v1/health/live` returns HTTP 200.
- `GET $API_URL/api/v1/health/ready` returns HTTP 200 and confirms database/PostGIS readiness.
- `GET $API_URL/api/v1/events` returns a valid empty or published-only page.
- `GET $API_URL/api/v1/map/events?west=30&south=20&east=45&north=40` returns a valid GeoJSON FeatureCollection.
- The frontend loads without CORS failures and shows an honest empty/no-live-data state until events are approved.
- Reviewer endpoints fail closed until OIDC settings and access-token roles are configured.

## Rollback and migrations

Use the last successful application deployment for an app rollback. Database migrations need a separate backup/restore plan; do not assume rolling back the app reverses a migration safely. Before production, document backup retention and recovery objectives and perform a restore test.

## Current limitations

- Render has not been provisioned by this change.
- The initial Alembic migration uses metadata-driven table creation. Replace it with explicit migrations and test upgrade/downgrade behavior before production.
- The OIDC provider and MFA policy are not configured; the analyst UI stays disabled until web and API identity settings are aligned. Source/ingestion endpoints are implemented but no source is approved or active by default. Scheduled ingestion, HDX/Copernicus/NASA/maritime connectors, raster/tile services, alerting, backup automation, and load/security tests are not completed.
