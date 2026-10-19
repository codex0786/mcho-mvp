# Phase 3 — Authentication and authorization gate

## Backend controls
- Provider-neutral OIDC/JWT access-token verification via configured JWKS.
- Asymmetric algorithm allowlist, exact issuer/audience checks, expiration/issued-at checks and required subject claim.
- Configurable role claim (including nested claims such as `realm_access.roles`).
- Separate reviewer and publisher permissions; no shared API key.
- Actor audit identity is `issuer|subject`; relevant actions carry issuer/role context.
- Missing OIDC configuration fails closed.

## Browser session controls (Phase 10 hardening)
- Server-side Authorization Code + PKCE flow: cryptographically generated state, nonce and verifier.
- Server-side discovery, token exchange, and ID-token signature/issuer/audience/nonce validation.
- Short-lived access token stored only in an HttpOnly cookie scoped to the same-origin API proxy; no token in local/session storage and no bearer token passed from browser JavaScript.
- Proxy ignores incoming browser Authorization headers, injects bearer token server-side, clears cookie on upstream 401, and enforces same-origin Origin on cookie-authenticated mutations.
- Local logout clears the application session cookie; it does not promise to terminate the identity-provider session.

## Verification
- API tests generate RSA signing keys and verify valid tokens, wrong audience, missing configuration, insufficient role and authorized role paths.
- GitHub Actions runs PostGIS migrations, API/worker tests, frontend typecheck/build and container builds.

## Deployment tasks still required
- Configure the real provider's client, exact redirect URI, API audience/resource and access-token role claims.
- Enforce MFA and provision the admin/reviewer/publisher groups in the identity provider.
- Test actual provider metadata/JWKS, sign-in, invalid state/nonce, token expiry and logout behavior in staging.
- Complete CSP/XSS testing, dependency scanning and a production security review.
