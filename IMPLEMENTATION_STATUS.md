# Implementation status — MCHO MVP

## Implemented and committed

- FastAPI + SQLAlchemy/PostGIS data model and Alembic migrations for source registry, source documents, events, evidence, revisions, review tasks/decisions, satellite scene metadata, humanitarian indicators, aggregate maritime metrics, alerts and audit logs.
- Public event APIs return only published, non-synthetic records; map endpoints return GeoJSON.
- OIDC/JWT API access-token validation against configured issuer, audience and JWKS, with asymmetric algorithm allowlist, expiration/issued-at checks, configurable role claim and reviewer/publisher/admin role gates.
- Browser authentication now uses server-side Authorization Code + PKCE, verified ID-token claims, short-lived HttpOnly access-token cookie scoped to the same-origin API proxy, no bearer token in browser storage, same-origin checks for cookie-authenticated mutations, and cookie clearing on logout/upstream 401.
- Publication requires a non-synthetic event, a positive post-revision independent review decision, an independent publisher, no open review task, and at least one source document individually approved and attached to an active source with reviewed terms and a retention policy. The latest editor, reviewer and publisher must be distinct principals for the version published.
- Source registration/activation requires explicit use metadata and audit logging. Evidence removal invalidates public events that no longer have qualifying evidence. A correction creates a new immutable revision, resets verification, removes the event from public status, and reopens review.
- Manual ingestion run model, per-source single-active-run constraint, checkpoints, external ID/content-hash deduplication, sanitized error ledger and run metrics.
- Read-only ReliefWeb API v2 metadata connector: pre-approved app name/country-scope gates, bounded fetch size/page count, totalCount pagination, overlap-window checkpointing, stable metadata normalization, canonical URL validation, review tasks and no article-body storage.
- Admin-only source registry and manual ingestion controls; analyst/reviewer/publisher/admin source-document review UI; human-authored event-draft path; separate verification and publication actions.
- Runtime liveness/readiness probes, safe request correlation logs, admin operational snapshot, staging smoke-test script, backup/restore and incident-response runbooks.
- Docker Compose local stack and Render Blueprint/deployment guide (cloud has not been provisioned).
- GitHub Actions CI for API/PostGIS migrations/tests, database-backed review-to-publication workflow tests, worker connector tests, OIDC BFF token-custody/CSRF tests, frontend typecheck/build, smoke-test/Compose validation and all three Docker image builds.

## Current validation status

Phase 10 BFF hardening passed GitHub Actions on commit `ed13c060d5693139adf7cb103413d080c03ff696`. Phase 11 independent review/publication gates passed on commit `251c89d119012963a20d86736e44f3969c93300b` across API/PostGIS tests, connector tests, frontend security/type-check/build and Docker builds. Phase 12 adds HTTP-level database-backed review-to-publication tests; its own CI run must pass before the new coverage is considered validated.

## Not yet operational

- No cloud services have been provisioned; no live public URL exists from this repository.
- The actual OIDC provider/tenant, client/resource, MFA policy and real user/role provisioning must be configured and tested in staging. The server-side BFF flow is code-complete but must be validated against the selected identity provider.
- ReliefWeb app name/country scope and source terms remain deployment tasks; no live feed is enabled by default. Other HDX HAPI, Copernicus, NASA FIRMS and licensed maritime integrations remain future work/guards.
- Ingestion-created source documents are review candidates, not event claims. The analyst workflow supports review and manual draft creation/linking from approved sources.
- Automated schedules, provider freshness alerts, production backup/restore drills, object storage, satellite raster processing/change analysis, maritime aggregation, alert routing, load/security testing and independent security review remain incomplete.
- The first migration uses legacy metadata-driven schema creation. Replace it with explicit production-safe operations before production use.
- The hosted Render Blueprint has not been applied and may incur recurring charges when provisioned.

## Trust and safety constraints

- A source record or satellite change candidate is not a verified event.
- No automatic event attribution or publication from source text.
- Missing reports, imagery or AIS coverage are not evidence that an event did or did not occur.
- Maritime output is limited to broad aggregate indicators; tactical live vessel tracking is out of scope.
- The platform is not for targeting or tactical military decisions.
