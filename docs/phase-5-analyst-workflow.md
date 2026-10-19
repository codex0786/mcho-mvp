# Phase 5 — Human-authored event drafting

## What is implemented

- OIDC-protected endpoint: `POST /api/v1/events/drafts/from-document/{document_id}`.
- Allowed roles: `analyst`, `reviewer`, or `admin`; publisher-only accounts do not create drafts by default.
- Source document must exist, be individually approved, and belong to an active source whose use status, terms URL, terms-review attestation and retention policy are all in force.
- The analyst provides a controlled event type, carefully worded summary, optional time range/country/location, explicit spatial uncertainty if coordinates are supplied, and a rationale.
- Time values must include a timezone offset; end time cannot precede start time; country codes follow uppercase ISO alpha-2 form; latitude/longitude must be paired.
- The action creates an event in `pending_review` / `unverified`, with attribution `unknown` and confidence `unassessed`.
- The source is linked as supporting evidence; the draft also has a `reported_claim` record, revision 1, a review task, and an audit entry identifying issuer and subject.
- The API response explicitly says `published: false`. No automated text-to-fact or text-to-event inference occurs.

## Request example

```json
{
  "event_type": "infrastructure_damage",
  "summary": "A reviewed source reports damage to a public building; the report does not establish who caused it.",
  "event_start": "2026-10-18T08:00:00Z",
  "event_end": null,
  "country_code": "LB",
  "latitude": 33.89,
  "longitude": 35.50,
  "spatial_uncertainty_m": 1500,
  "rationale": "The location is approximate; the cited report gives no independent geolocation confirmation."
}
```

Coordinates are optional. When absent, the record may still be country/time-filterable but will not be represented as a precise map point. Never fabricate coordinates to fill a map gap.

## Browser workspace implemented

The `/analyst` page now includes:
- OIDC login using Authorization Code + PKCE, an identity callback route and logout.
- Runtime public configuration (`/api/public-config`) so the identity-provider client settings need not be compiled into the image.
- API-side identity validation, source document review-state filter, source metadata/canonical-link panel, draft form and explicit warnings that drafts stay unpublished.
- Role-aware draft controls; the API independently enforces roles and source/document eligibility.

The browser workspace is intentionally disabled until the real OIDC authority, client ID/resource, API issuer/audience/JWKS and exact redirect URLs are configured. It does not accept pasted tokens. A full reviewer decision UI and a server-side HttpOnly-cookie BFF session remain follow-up hardening items.


## Reviewer queue and separate publication

The analyst console exposes `GET /api/v1/reviews/tasks?status=...` for reviewer/publisher/admin roles. Each task includes a human-readable event or source-document title, canonical source URL where applicable, event status and verification state. Reviewer/admin roles may save one of the allowed review decisions with a required rationale. This cannot publish an event.

Completed event tasks with eligible verification state can be shown to publisher/admin roles through the completed-task filter. The explicit **Publish separately** action calls the publisher-protected publication endpoint; the API rechecks evidence, source use terms, document approval and high-impact verification rules. UI visibility is not an authorization boundary.
