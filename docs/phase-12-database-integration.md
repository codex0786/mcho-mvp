# Phase 12 — Database-backed publication workflow tests

## Why this phase exists

The domain helpers can be unit-tested without infrastructure, but publication is a chain of API/database operations: revision records, review tasks, decisions, evidence eligibility, and the final publication audit all need to agree. The CI PostGIS service now supports an HTTP-level integration test of that full path.

## Test setup

- The tests run only when `MCHO_INTEGRATION_TESTS=1`, so a developer without a local PostGIS database can still run the unit suite.
- CI enables the flag and runs the tests against the same temporary PostGIS database that has just passed Alembic migrations.
- Each test uses a savepoint-backed SQLAlchemy session on an outer transaction, so test rows are rolled back and cannot leak into other tests.
- Authentication dependencies are overridden with distinct test principals; the access-policy logic itself is not mocked.

## Scenarios covered

1. An editor attempts to review their own event version: HTTP 409, no review decision recorded.
2. A different reviewer verifies the event: the decision is recorded, but the event remains unpublished.
3. The same reviewer tries to publish: HTTP 409.
4. A different publisher publishes the independently reviewed version: HTTP 200, publication response includes revision number, decision ID and evidence eligibility count.
5. A version changes after an approval decision: publication is rejected until a new review decision is recorded for the latest revision.

The fixture includes a source that is active with reviewed permitted-use metadata, an individually approved source document, the event evidence link, immutable revision 1, and an open event review task. That means the happy-path assertion exercises the evidence and provenance gate, not only role checks.

## CI gate

The API job must apply migrations successfully, compile the application/tests, and pass both unit/policy tests and the database-backed publication workflow tests. The complete repository workflow also runs ReliefWeb no-network tests, OIDC BFF tests, frontend production type-check/build, Compose/smoke-script checks, and Docker image builds.

## Remaining production verification

- Run the same draft → review → publish flow in staging with real OIDC accounts assigned to three distinct people.
- Confirm role provisioning does not grant one individual multiple identities that bypass distinct-principal checks.
- Exercise correction/re-review/republication against real staging data before any public production release.
