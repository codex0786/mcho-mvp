# Phase 11 — Independent review and publication controls

## Policy

Every public event revision must pass a version-specific workflow:

1. An analyst or publisher creates an immutable revision. The revision records the editing principal as `issuer|subject`.
2. A different principal reviews that exact version. The latest editor cannot approve their own revision.
3. A third principal with the publisher/admin role publishes. The publisher must differ from the latest editor and the reviewer.
4. The review decision must be a positive `verify` or `accept_provisional` decision, must match the event's current verification status, and must have been recorded after the latest revision.
5. No event may be published while any review task remains open. Synthetic, withdrawn, already-published, unverified and evidence-ineligible records remain blocked.
6. A correction creates another immutable revision, resets verification to `unverified`, moves the event out of the public state, and reopens a review task. Publisher-supplied correction data cannot set the event to verified/provisional.

High-impact event types continue to require verified status (not provisional) before publication.

## API behavior

- Review decisions return HTTP 409 if the reviewer is the latest editor.
- Publication returns HTTP 409 if there is no positive post-revision decision, the latest decision is not an approval, the reviewer/publisher separation rule fails, the event has an open review task, or the decision predates the current revision.
- Repeat publication is rejected; republishing requires a correction/new revision and fresh review.
- Every publication audit record now records the revision number and specific review-decision ID, along with reviewer, publisher, verification and eligible-evidence counts.
- Correction audit logs state whether a new review task was opened.

These are server-side controls; hiding buttons in the UI is not an authorization boundary.

## Tests

The API policy tests cover same-user review, same-user publication, publisher/reviewer collision, independent three-person flow, approval-decision types, decision timestamp ordering, and attempts by a publisher to self-assert verification status during correction.

## Limits

- This gate is only as strong as identity-provider account governance. One human holding multiple accounts can bypass a naive distinct-subject rule; the organization should provision individual accounts and monitor privileged role assignment.
- The test suite exercises the domain policy helpers and migration/build gates. A real provider plus database-backed staging review/publish drill remains required before production.
