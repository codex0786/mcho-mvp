# Render pilot deployment

This guide covers the **paid** pilot Blueprint at `deploy/render-paid-pilot.yaml` (API, frontend, Celery worker, private Key Value queue and PostgreSQL database). For the no-cost setup used today, see [the free-tier guide](./deploy-free-tier.md); the root `render.yaml` is that free Blueprint. The Blueprint is infrastructure-as-code only; no resources are provisioned by a Git commit.

## Cost and scope

**Review current Render pricing, region, plans and persistent-storage settings before applying the Blueprint.** Applying it provisions cloud resources that may incur recurring charges. The current Singapore configuration is a small pilot default, not a load-tested production sizing decision. Review latency, data-handling requirements and provider terms before use.

The Blueprint does not configure a real OIDC tenant, activate data sources or enable scheduled polling. Do not describe the observatory as live-data enabled until the identity provider, source-use approval, QA and freshness monitoring are configured and tested.

## Apply the Blueprint

1. In Render, choose **New → Blueprint**.
2. Connect `https://github.com/codex0786/mcho-mvp` and select branch `main`.
3. Review every service, region, plan and recurring charge before confirming provisioning.
4. After creation, confirm the API, worker, web service, private Key Value and database all deploy. Inspect the API pre-deploy logs to confirm Alembic migrations completed.
5. Set `MCHO_MAP_STYLE_URL` on `mcho-web` to a permitted MapLibre style JSON URL if you want a basemap; blank is an intentional no-basemap state.
6. Configure `MCHO_OIDC_AUTHORITY`, `MCHO_OIDC_CLIENT_ID` and optionally `MCHO_OIDC_RESOURCE` for `mcho-web`. Configure the matching `OIDC_ISSUER`, `OIDC_AUDIENCE`, and `OIDC_JWKS_URL` for `mcho-api`. Register the exact `https://<mcho-web-host>/api/auth/callback` redirect URI with the identity provider. The server-side flow clears the MCHO cookie on sign-out; provider logout is a separate identity-provider session and may remain active. Require MFA for privileged roles.
7. Before enabling ReliefWeb ingestion, set the same `RELIEFWEB_APPNAME` and `RELIEFWEB_COUNTRIES` values on both `mcho-api` and `mcho-worker`. The admin panel reports API-side configuration only, not worker equality or provider connectivity.
8. Keep `CORS_ORIGINS` blank unless you deliberately need browser clients to call the API directly. The MCHO web application uses a same-origin backend proxy, so it does not depend on browser CORS to reach the API.
9. Open the Render-assigned `mcho-web` public URL.

The browser uses a same-origin Next.js backend proxy. The proxy ignores browser-supplied Authorization headers, reads the short-lived access token from a path-scoped HttpOnly cookie, injects it server-side, forwards only content-type/accept/request-id headers, and uses no-store cache semantics. State-changing cookie-authenticated calls require a same-origin Origin header. Never pass a token in a URL or log a bearer token. The OIDC authorization-code callback is `https://<mcho-web-host>/api/auth/callback`; Render's `RENDER_EXTERNAL_URL` provides the web origin unless `MCHO_WEB_ORIGIN` is set for a custom domain.

## Configuration and security

- Managed PostgreSQL URLs using `postgres://` or `postgresql://` are normalized to the installed SQLAlchemy `postgresql+psycopg://` driver format. The API honors the platform-provided `PORT`.
- Keep Redis-compatible Key Value and database connections private. The Blueprint uses internal service references for worker/API access.
- `NEXT_PUBLIC_*` values are browser-visible and must never contain secrets.
- The OIDC provider and MFA policy are not configured by default. The analyst workspace stays disabled until the web client/authority and API issuer/audience/JWKS are aligned.
- ReliefWeb metadata ingestion remains disabled until an approved app name, explicit country scope, a reviewed/active source record and a retention policy are configured. The adapter requests metadata/links only, not source article bodies.
- HDX HAPI, Copernicus, NASA FIRMS and maritime aggregation are not enabled. Do not interpret satellite hot spots as verified attacks or expose tactical vessel tracks.
- Put source credentials only in the host’s secret environment settings after reviewing source terms and least-privilege access.

## Smoke tests

After deployment, run the repository smoke test from a machine that can access both public URLs:

```bash
API_URL="https://<mcho-api-host>" WEB_URL="https://<mcho-web-host>" ./scripts/smoke-test.sh
```

The script checks live/ready health, PostgreSQL/PostGIS/Redis readiness, event JSON shape, GeoJSON map shape, the web homepage, runtime public config and the same-origin API proxy. A passing smoke test proves basic wiring only—it is not evidence that any feed is active or that event records are accurate.

You can also check individual endpoints:

- `GET $API_URL/api/v1/health/live` returns HTTP 200.
- `GET $API_URL/api/v1/health/ready` returns HTTP 200 and confirms PostgreSQL, PostGIS and Redis readiness.
- `GET $API_URL/api/v1/events?page_size=1` returns a valid published-only page.
- `GET $API_URL/api/v1/map/events?west=30&south=20&east=45&north=40` returns a valid GeoJSON FeatureCollection.
- `GET $WEB_URL/api/public-config` returns runtime public configuration but no secrets.
- `GET $WEB_URL/api/backend/api/v1/health/live` verifies the same-origin proxy reaches the API.

## Operations, backups and incident response

- Read the [operations and readiness guide](./phase-9-operations.md).
- Configure backup retention and rehearse recovery using the [backup/restore runbook](./runbooks/backup-restore.md); the Blueprint does not automatically configure a backup policy.
- Use the [incident-response runbook](./runbooks/incident-response.md) for dependency outages, ingestion failures, data corrections and credential events.

## Rollback and migrations

Use the last successful application deployment for an application rollback. Database migrations need an independent backup/restore plan; rolling back an app does not necessarily reverse a migration safely. Before production, document backup retention/recovery objectives and conduct a restore test against an isolated database.

## Remaining limitations

- Render has not been provisioned by this repository change.
- The original migration still uses metadata-driven schema creation; replace it with explicit production migration operations in a dedicated future step.
- The actual OIDC provider/MFA policy, roles and client redirect registration are deployment-specific and remain unconfigured.
- No active source is enabled by default. Scheduled ingestion, HDX/Copernicus/NASA/maritime connectors, raster/tile services, alerting, backup automation, load tests and independent security review remain incomplete.
