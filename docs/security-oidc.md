# OIDC authentication and authorization

MCHO is a resource server: it validates an access token issued by an OIDC/OAuth identity provider. It does not issue tokens itself. The API does **not** treat an ID token as an API access token.

## Configuration

Set these variables in the API service environment. The values are deployment-specific and must not be guessed or committed as secrets.

| Variable | Meaning |
|---|---|
| `OIDC_ISSUER` | Exact `iss` claim expected in access tokens. Match slash/case exactly. |
| `OIDC_AUDIENCE` | API/resource audience, recommended identifier `mcho-api`. |
| `OIDC_JWKS_URL` | HTTPS URL of the trusted issuer's JSON Web Key Set. Usually `jwks_uri` in its OIDC discovery document. |
| `OIDC_ROLE_CLAIM` | Claim name containing roles; default `roles`. Supports dotted nested paths such as `realm_access.roles` and namespaced claims. |
| `OIDC_ALGORITHMS` | Comma-separated allowlist of asymmetric signing algorithms; default `RS256`. HMAC algorithms are rejected. |

The issuer/JWKS URL must use HTTPS in production. Missing or invalid server configuration fails closed with HTTP 503. Missing bearer tokens or invalid/expired tokens return 401. A valid token without the required role returns 403.

## Configure the identity provider

1. Create an API/resource entry with audience `mcho-api`.
2. Configure clients to request a **JWT access token** whose audience is `mcho-api`; do not pass an ID token.
3. Configure the access-token role claim to contain an array of role strings (preferred) or a space-separated role string. Assign roles in the identity provider, not from user-controlled request fields.
4. Require MFA for reviewers, publishers and administrators in the identity provider.
5. Copy the exact issuer and JWKS URI from provider discovery/metadata and set the variables above in the host dashboard.
6. Use a short access-token lifetime (for example 5–15 minutes), and follow the provider's key-rotation policy. MCHO caches the JWKS document for five minutes.
7. Test a reviewer token and publisher token with the correct audience. Also test wrong issuer/audience, expired tokens, missing role claims and revoked users.

Do not enable authorization based on client-supplied `X-Role` headers or editable profile fields. The API trusts roles only when they are inside a cryptographically validated token from the configured issuer.

## Roles

| Role | Allowed operation |
|---|---|
| `analyst` | No privileged review/publish API access yet; analyst candidate-creation endpoints will be added with the workbench. |
| `reviewer` | Review queue and review decisions; can verify, provisionally accept, dispute, reject or request more evidence. |
| `publisher` | View the review queue and publish/correct events when all evidence and status gates pass. |
| `admin` | Can perform reviewer and publisher actions. Admin membership must be tightly controlled. |

The role-claim mapping is configurable because providers use different schemas. For example, Keycloak can use `realm_access.roles`; providers that issue a custom namespaced claim can configure that exact claim path. Roles remain case-sensitive.

Audit records identify the actor using the pair `issuer|subject`, and record role/issuer context where relevant. This avoids confusing subjects from different trusted issuers.

## Current boundaries

- The public website remains readable without a token.
- The `/analyst` workspace uses a server-side OIDC Authorization Code + PKCE flow. The Next.js server keeps the PKCE verifier/state/nonce in short-lived HttpOnly cookies, exchanges the authorization code server-side, verifies the ID token signature/issuer/audience/nonce, and stores the short-lived API access token in an HttpOnly, Secure (production), SameSite=Lax cookie scoped to the same-origin backend proxy. Browser JavaScript does not receive the bearer token. The proxy strips browser-supplied Authorization headers, reads the token cookie server-side, and injects the validated session token when forwarding to the API.
- The Render Blueprint does not invent an issuer, client ID or secret. Configure `OIDC_ISSUER`, `OIDC_AUDIENCE` and `OIDC_JWKS_URL` for `mcho-api`; configure `MCHO_OIDC_AUTHORITY`, `MCHO_OIDC_CLIENT_ID` and optional `MCHO_OIDC_RESOURCE` for `mcho-web`. The expected API audience must match the access token audience and, when used, the requested resource.
- Do not configure an HMAC/shared secret as the JWT signing key.
- Tests use locally generated RSA keys and a mocked JWKS source; staging must additionally be tested against the real provider's JWKS, issuer, audience and role claims.

## Security checks before production

- [ ] OIDC issuer, audience, JWKS endpoint and roles claim are configured in production.
- [ ] MFA is enforced for privileged provider accounts.
- [ ] Access tokens have short expiration and correct audience.
- [ ] Invalid/expired tokens and missing roles are rejected.
- [ ] Reviewer and publisher actions are attributable and audited.
- [ ] Provider outage behavior and signing-key rotation are tested.
- [ ] Account removal/role revocation behavior is documented.
- [ ] Register the exact `https://your-web-host/api/auth/callback` redirect URI at the provider. Local MCHO sign-out clears the app cookie; it does not necessarily sign the user out of the identity provider.
- [ ] Production Content-Security-Policy, XSS prevention, browser security testing and token-expiration behavior are validated.
- [x] Access tokens are kept in a server-side HttpOnly cookie and never returned to browser JavaScript; keep short access-token lifetimes.


## Browser flow and deployment settings

The analyst workspace uses server-side Authorization Code + PKCE. State, nonce and PKCE verifier are generated with cryptographically secure randomness and stored briefly in HttpOnly cookies scoped to the callback. The server discovers the issuer metadata over HTTPS, exchanges the code without embedding a client secret, verifies the ID-token signature and claims using the provider JWKS, then places only the short-lived API access token in an HttpOnly cookie scoped to `/api/backend`. Access/ID/refresh tokens are not returned by the runtime-config endpoint and are not stored in browser Web Storage. No refresh token is persisted; after token expiry, the user signs in again. This reduces token extraction risk but does not replace a strict Content-Security-Policy, XSS prevention, dependency review or browser security testing.

The frontend loads these runtime values from `GET /api/public-config`, so the same frontend image can be promoted between environments:

- `MCHO_OIDC_AUTHORITY`: OIDC authority URL used for discovery
- `MCHO_OIDC_CLIENT_ID`: public OIDC client identifier registered for the authorization-code flow; it is not a client secret
- `MCHO_OIDC_RESOURCE`: optional resource/audience request parameter
- `MCHO_WEB_ORIGIN`: optional exact public origin; Render's `RENDER_EXTERNAL_URL` is used when a custom origin is not configured
- `MCHO_MAP_STYLE_URL`: approved MapLibre style URL

API trust settings remain server-side. `OIDC_ISSUER` must exactly match the access-token `iss` claim; `OIDC_AUDIENCE` must match the API access-token `aud`; `OIDC_JWKS_URL` must be the trusted issuer's JWKS endpoint. A client-side role display is informative only—API role checks are authoritative.
