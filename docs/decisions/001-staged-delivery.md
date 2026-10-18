# ADR 001: Staged delivery and initial hosting posture

- **Status:** Accepted
- **Decision:** Stabilize and test the current monorepo before adding live data; deploy a staging environment before production.
- **Initial app shape:** Next.js/MapLibre frontend, FastAPI API, PostgreSQL/PostGIS, Redis-backed Celery workers, and private object storage.
- **Hosting default:** Evaluate Render for the pilot because its managed services align with the current service model. Do not provision billable resources until the owner reviews expected costs and selects a plan.
- **Trust boundary:** Public APIs expose only approved, non-synthetic publications. Ingestion outputs are candidates. Review decisions and publication actions remain separate.
- **Source posture:** Integrate one source at a time and preserve licensing, provenance, time, checksum, version and freshness. An accessible API is not proof that data can legally be redistributed.
- **Satellite posture:** Automated change candidates are not confirmed damage without human review.
- **Maritime posture:** Aggregate port/area metrics only; no tactical live vessel tracks or targeting support.
- **Consequences:** Delivery takes more steps than a quick demo deployment, but build and trust-control gaps are surfaced before public operation.
