# Phase 8 — Admin source registry and manual ingestion

## Admin surface

The `/analyst` page includes an admin-only source registry and manual-ingestion panel. Every operation is protected again by the API's `admin` role; hiding a button in the browser is not the authorization control.

Supported operations include source registration (inactive by default), terms/retention edits, terms-review attestation, source approval, activation/deactivation, manual ingestion queueing and run status/count summaries.

## Provider settings and safety

The admin configuration endpoint is `GET /api/v1/ingestion/configuration`. It reports whether the API environment has a non-empty `RELIEFWEB_APPNAME` and `RELIEFWEB_COUNTRIES`; it never returns the app-name value. It does not test network connectivity or inspect worker settings.

For hosted operation, configure identical `RELIEFWEB_APPNAME` and `RELIEFWEB_COUNTRIES` values on both `mcho-api` and `mcho-worker`. The API refuses to queue runs if its own provider configuration is incomplete. The worker independently refuses to fetch if its settings are missing. After queueing, verify run status and worker logs—the HTTP 202 response only means the task was accepted for dispatch.

Changing a source's terms URL resets its use status to `unreviewed`, clears the previous reviewer attestation and deactivates the source. Administrators must review the new terms and explicitly approve again. Deactivation may remove events from the public feed when no other qualifying evidence remains.

## Operator sequence

1. Configure the actual provider app name and a deliberate country scope in API and worker settings; redeploy both services.
2. Register the source and enter the exact terms URL, owner/contributor and retention/use note.
3. Read terms for access, attribution, reuse/redistribution, rate limits and retention. Tick the explicit attestation and apply use approval.
4. Activate the source only after terms review and retention policy are complete.
5. Queue one manual run and inspect status/counts. If API and worker settings differ, the worker may skip the task.
6. Review each source document individually. Source-document approval is not event verification.
7. Create a human-authored event draft from an approved document, preserve uncertainty, review separately, then publish through the explicit publisher/admin control only after server-side evidence/status gates pass.

## Current limits

- No periodic polling or automatic alerting on stale sources is configured; runs are manual.
- The admin endpoint cannot prove worker/API environment equality or verify the provider accepts the configured app name.
- The terms attestation is a human responsibility control, not an automated determination of legal rights.
- No source is approved/active by default and no live feed is enabled by default.
