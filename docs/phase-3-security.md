# Phase 3 — Authentication and authorization gate

## Implemented
- Provider-neutral OIDC/JWT access-token verification using a trusted configured JWKS endpoint.
- Signature validation, configured asymmetric algorithm allowlist, exact issuer and audience validation, expiration and issued-at checks, and a required subject.
- Configurable role claim (including nested claims such as `realm_access.roles`).
- Separate reviewer and publisher permissions. Review decisions no longer accept the legacy shared API key.
- Identity attribution uses the configured issuer and subject; relevant actions include role/issuer audit context.
- Fail-closed behavior when OIDC configuration is absent.

## Verification
- Tests generate local RSA signing keys and verify valid token, wrong audience, missing configuration, role denial and role acceptance cases.
- CI runs the API tests and PostGIS migration; remote CI status is linked from the repository README when applicable.

## Not yet complete
- No concrete identity provider is configured; the owner must choose/create its tenant/resource and map roles.
- No browser login UI, token refresh, analyst workbench or end-to-end login test is implemented.
- MFA policies, account lifecycle, provider-side role provisioning and revocation are enforced/configured at the identity provider and remain deployment tasks.
