# Implementation status — MCHO MVP

## Implemented and committed

- FastAPI + SQLAlchemy/PostGIS data model and Alembic migrations for source registry, source documents, events, evidence, revisions, review tasks/decisions, satellite scene metadata, humanitarian indicators, aggregate maritime metrics, alerts and audit logs.
- Public event APIs return only published, non-synthetic records; map endpoints return GeoJSON.
- OIDC/JWT access-token validation against configured issuer, audience and JWKS, asymmetric algorithm allowlist, expiry/issued-at checks, configurable role claim and reviewer/publisher/admin role gates. Authentication fails closed when not configured.
- Publication requires a non-synthetic event, allowed review status and at least one source document that is individually approved and attached to an active source with reviewed terms and a retention policy.
- Source registration and activation require explicit license/use metadata and audit logging. When an evidence source or document is deactivated/disputed, public events without qualifying evidence are removed from public status and audited.
- Manual ingestion run model, single-active-run constraint per source, checkpoints, external ID/content-hash deduplication, sanitized error ledger and run metrics.
- Read-only ReliefWeb API v2 metadata connector: pre-approved app name/country-scope checks; bounded request size/page count; totalCount-based pagination; overlap-window checkpointing; stable metadata normalization; canonical source URL validation; source-document review tasks; no article body download/storage.
- Admin-only endpoints to register/review source configuration, queue connector runs and inspect run/error status. Reviewer/analyst/publisher roles can inspect source-document metadata and links.
- OIDC-gated human-authored event draft endpoint from an individually approved source document. Creates a reported-claim row, supporting evidence link, immutable initial revision, review task and audit record; leaves the event pending review and unpublished.
- Docker Compose local stack and a Render Blueprint/deployment guide (not provisioned).
- GitHub Actions pipeline for API compile/migration/tests on PostGIS, no-network connector tests, frontend typecheck/production build and API/worker/web Docker builds.

## Current validation status

Phase 4 implementation is being validated via GitHub Actions on the latest commit. The last completed Phase 3 run passed API/PostGIS tests, frontend typecheck/build and all container builds. Do not infer that Phase 4 passed until its new workflow run completes successfully.

## Not yet operational

- No cloud services have been provisioned; no live public URL exists from this repository.
- OIDC provider/tenant, MFA policy, real roles and browser login token handling are not configured.
- ReliefWeb app name, country scope and source terms are not configured; no live feed is enabled. Other HDX HAPI, Copernicus, NASA FIRMS and licensed maritime integrations remain future work/guards.
- Ingestion-created source documents are review candidates, not event claims. The API now supports manual draft creation/linking from approved documents; the full analyst workbench and browser OIDC login/session are still needed for end-to-end workflows.
- Automated schedules, provider freshness alerts, production backups/restore testing, object storage, satellite raster processing/change analysis, maritime aggregation, observability dashboards, load tests and security assessment remain incomplete.
- The first migration uses metadata-driven schema creation. Replace that legacy initial migration with explicit production-safe operations in a dedicated future migration before production use.

## Trust and safety constraints

- A source record or satellite change candidate is not a verified event.
- No automatic event attribution or publication from source text.
- Missing reports, imagery or AIS coverage are not evidence that an event did or did not occur.
- Maritime output is limited to broad aggregate indicators; tactical live vessel tracking is out of scope.
- The platform is not for targeting or tactical military decisions.
