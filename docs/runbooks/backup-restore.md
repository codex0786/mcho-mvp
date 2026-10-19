# Runbook — PostgreSQL/PostGIS backup and restore

## Status

MCHO does not yet provision backup policies automatically. The owner must configure and verify the selected hosting/database plan's actual backup, retention and point-in-time recovery capabilities in the provider dashboard. Do not assume a specific plan includes a feature without checking the account and plan in use.

Before production, define and approve:
- **RPO** — acceptable maximum amount of data loss in time.
- **RTO** — acceptable time to restore service.
- Who can initiate, approve and verify a restore.
- Retention duration and where backup copies are protected.
- How restore access is audited and how long temporary restored data is retained.

## Routine checks

1. Verify the latest scheduled backup/snapshot completed successfully and record its timestamp/retention.
2. Alert if the backup is older than the agreed RPO or if the provider reports a failed backup.
3. Review privileged access and provider audit history for restore/backup operations.
4. Keep a recent export of schema/migration metadata and deployment version alongside recovery notes, but never store credentials in the notes.

## Restore rehearsal (isolated target only)

1. Open an incident/recovery ticket and identify the target restore point.
2. Restore the provider snapshot/PITR to an **isolated new database**. Do not overwrite the live database as a first step.
3. Connect using the same supported PostgreSQL major version and verify the PostGIS extension: `SELECT PostGIS_Full_Version();`.
4. Check Alembic state with `alembic current`; inspect migration history and only apply migrations after validating the restored version.
5. From an isolated application deployment, check `/api/v1/health/ready`, the public event page, and the GeoJSON map endpoint. Confirm the response uses the restored database, not production.
6. Verify relational consistency: source documents/evidence, event revisions, review tasks/decisions, audit records, ingestion runs/checkpoints and publication states. Compare expected table counts and review a sample of recent records.
7. Run the staging smoke test against the isolated API/web URLs. The script also checks web proxy wiring.
8. Record duration, data-loss window, validation results, deviations and follow-up actions. Update the operational recovery plan.

## Production recovery

Use the approved incident procedure and a change window. Preserve the pre-restore database/snapshot where practical. Do not make the restored database public until the data steward validates corrections, publication state and audit continuity. Treat Redis as a disposable task queue: after database recovery, inspect `queued`/stuck ingestion runs and reconcile them carefully before manually re-queueing. Do not assume a task queue message is proof a provider fetch occurred.

## Recovery acceptance

- The tested restore point is within the agreed RPO.
- Full service is restored within the agreed RTO.
- API readiness, PostGIS, Redis dispatch, frontend proxy and core read operations pass.
- Published events have valid evidence, source-document review and audit history.
- Any run/task redelivery is reconciled without duplicate external records or auto-publication.
