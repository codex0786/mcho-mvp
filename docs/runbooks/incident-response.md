# Runbook — MCHO incident response

## Severity and initial triage

Treat availability incidents, security incidents, provider/data-quality incidents and publication-integrity incidents separately. Record incident start time, affected environments, operator and request IDs, but do not copy bearer tokens, provider secrets or user cookies into the incident ticket.

1. Check `GET /api/v1/health/live` and `GET /api/v1/health/ready`.
2. Review API JSON logs using `X-Request-ID`, route path, status and latency. Request logs intentionally omit query strings, bodies and authorization headers.
3. Check the admin operational snapshot: active/queued runs, recent run status counts, last checkpoint timestamps and source-term states.
4. Confirm whether the service has been deployed and provider settings are configured. An empty event response, missing imagery or absent checkpoint is not evidence that an incident did or did not occur.

## API/database/queue outage

- If liveness fails, check container exit/restart history and deploy logs.
- If readiness reports Postgres unavailable, verify the managed database status, connection limit, network allow-list and credentials in the hosting secret store. Do not print DSNs to logs/tickets.
- If PostGIS is unavailable, inspect extension/migration state before making changes.
- If Redis is unavailable, the API may serve already stored reads but manual ingestion dispatch will fail. Restore queue connectivity before re-queueing; inspect the database run record for `queue_failed` first.
- After recovery, run the staging smoke script and record request IDs and outcome.

## Ingestion failure or stale checkpoint

1. Open the ingestion run summary by run ID; capture status and aggregate counts.
2. Use the admin error endpoint to review sanitized error categories and row hashes. Raw provider payloads are intentionally not written to the error ledger.
3. Check provider terms/approval, app name/country-scope configuration in API and worker, deployment versions, provider rate limits and worker logs.
4. A queued run is not a successful fetch. Confirm terminal status and counters before concluding it ran.
5. Fix source configuration/adapter issues, deploy and queue a new manual run. Do not enable periodic polling as an ad hoc incident workaround.
6. Review newly ingested source documents individually; do not create or publish facts automatically from report metadata.

## Publication/data-integrity incident

- If a source/document becomes disputed, restricted or deactivated, preserve audit records and make the immediate public-availability decision through the source review controls.
- Use the publisher-protected correction/withdrawal path; preserve event revision history and rationale.
- Do not silently edit a claim or infer an actor from imagery/fire detections.
- After a correction, independently verify that eligible evidence remains and that publication state reflects the reviewed status.
- If a public event is inaccurate, preserve the citation, revision, reviewer rationale and exact action time for later audit.

## Security/credential incident

- Rotate the affected provider or identity-provider secret in its authoritative dashboard, not in git.
- Invalidate/revoke identity-provider accounts/tokens according to the provider policy.
- Inspect audit records and request IDs while limiting access to incident responders.
- Do not paste JWTs, client secrets, DSNs, report contents or sensitive personal data into logs or tickets.
- Keep production OIDC issuer/audience/JWKS configuration fail-closed; do not temporarily bypass role validation to restore a workflow.
