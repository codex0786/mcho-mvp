# Phase 1 — Build stabilization and quality gates

## Objective
Make the repository build and test consistently before exposing services or enabling real data ingestion.

## Changes in this phase
- Add GitHub Actions CI for Python compile/tests, Alembic migration against PostGIS, frontend typecheck and Next.js production build.
- Ensure the frontend Docker image does not reference a missing lockfile and includes a public directory.
- Pass Next.js `NEXT_PUBLIC_*` values as Docker build arguments; runtime environment variables alone are too late for values embedded during a Next.js build.
- Construct database URLs from separate fields when no managed-host `DATABASE_URL` is supplied, safely URL-encoding special characters in passwords.
- Fail closed when the reviewer key is unconfigured, validate review decisions, and test the authorization contract.
- Make source records inactive by default. Publication requires at least one linked item from an active source with an explicitly reviewed permitted-use status.
- Applying a review decision updates an event's verification state but never publishes it directly. Disputed/rejected claims are removed from public status immediately.

## Acceptance criteria
- [ ] GitHub Actions API job passes, including PostGIS migration.
- [ ] GitHub Actions frontend typecheck and build pass.
- [ ] A reviewer decision changes the event state according to policy and does not itself publish it.
- [ ] Missing reviewer configuration returns 503; incorrect credentials return 403.
- [ ] Publication rejects synthetic records, withdrawn records, events with no evidence, and evidence from inactive/unreviewed sources.
- [ ] Docker Compose local configuration is reviewed against the chosen staging environment.

## Known limits after this phase
- Production OIDC/MFA and role-based authentication are not configured. The shared-key mechanism remains a temporary non-production control.
- No real source connector is enabled; connector classes remain configuration guards.
- The frontend lockfile is still missing because package registry access was unavailable in the local execution environment. Generate and commit `apps/web/package-lock.json` before production to make dependency resolution reproducible.
- Docker is unavailable locally and npm package registry access timed out, so full image and frontend builds could not be verified here. GitHub Actions is configured to perform those checks on network-enabled runners.
- The Alembic first migration still uses metadata-driven table creation; replace with explicit migration operations before production and test both fresh installs and upgrades.
