# Phase 10 — Browser-session hardening (BFF)

## Problem

A pure browser OIDC client keeps the access token in JavaScript-accessible Web Storage. An XSS bug or unsafe third-party script could extract a bearer token and reuse it outside the browser. The same-origin proxy already existed, so this phase moves the code exchange and token custody into the Next.js server.

## Flow implemented

1. The browser navigates to `GET /api/auth/login`.
2. The server validates runtime configuration and discovers OIDC metadata over HTTPS.
3. It creates independent high-entropy state, nonce and PKCE verifier values, stores them in short-lived HttpOnly cookies scoped to `/api/auth/callback`, and redirects to the authorization endpoint with S256 PKCE.
4. The identity provider returns to `GET /api/auth/callback`. The server compares state, exchanges the code using the verifier, discovers the provider JWKS, and verifies the ID token's signature, issuer, client audience, expiration and nonce.
5. The API access token is placed in a short-lived HttpOnly, SameSite=Lax cookie scoped only to `/api/backend`. It is never returned to client JavaScript and no ID/refresh token is persisted.
6. The analyst UI calls the same-origin proxy without an Authorization header. The proxy ignores browser-supplied Authorization headers, reads the access cookie server-side, injects the bearer token, and forwards only needed headers to the configured API origin.
7. An upstream API 401 clears the cookie. Explicit sign-out clears the local MCHO session cookie. Identity-provider logout may remain active and is not misrepresented as terminated.
8. State-changing requests using a session cookie must carry a same-origin Origin header. Proxy and login responses are not cacheable; request/response paths do not log tokens.

## Cookies

| Cookie | Scope | Purpose | Lifetime |
|---|---|---|---|
| `mcho_oidc_state` | `/api/auth/callback` | Match authorization response to login initiation | 10 minutes |
| `mcho_oidc_nonce` | `/api/auth/callback` | Bind ID token to login initiation | 10 minutes |
| `mcho_oidc_verifier` | `/api/auth/callback` | Complete S256 PKCE code exchange | 10 minutes |
| `mcho_access_token` | `/api/backend` | Server-side API authorization | `min(expires_in, 1 hour)` |

Cookies are HttpOnly and SameSite=Lax. Secure is enabled when the web origin is HTTPS. The only HTTP exception is explicit localhost development/Compose use.

## Configuration

- `MCHO_OIDC_AUTHORITY`: identity-provider issuer/authority for discovery.
- `MCHO_OIDC_CLIENT_ID`: public client ID registered for Authorization Code + PKCE; no client secret is required or placed in the browser.
- `MCHO_OIDC_RESOURCE`: optional API resource/audience hint sent to authorize and token endpoints.
- `MCHO_API_ORIGIN`: server-only upstream API base origin.
- `MCHO_WEB_ORIGIN`: optional exact external origin, useful for a custom domain. If blank on Render, the service's `RENDER_EXTERNAL_URL` is used.
- The API separately requires matching `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL` and role claim configuration.

Register exactly `https://your-web-host/api/auth/callback` at the identity provider. Do not register the unused legacy UI path `/auth/callback`.

## Local and production validation

1. Configure an OIDC provider test client with code flow, PKCE S256, an API access-token audience/resource and role claims. Require MFA for reviewer/publisher/admin groups in the provider.
2. Register the exact callback URI and configure the web/API environment variables. For local Docker Compose, use the local origin `http://localhost:3000`; cookies are not Secure only for this localhost case.
3. Verify the authorization request includes state, nonce and S256 code challenge.
4. Exercise success and failure cases: missing/changed state, provider error, invalid nonce, wrong ID-token issuer/audience/signature, token endpoint outage, API 401, missing role and logout.
5. In browser devtools, confirm there is no access token in local/session storage, local JavaScript state or response JSON. The access cookie must be HttpOnly and Path=/api/backend.
6. Confirm cross-origin POST/PATCH requests are rejected while a same-origin analyst/reviewer/publisher request succeeds when the API role permits it.
7. Run `npm run test:auth`, `npm run typecheck`, `npm run build` and the full GitHub Actions workflow. The automated tests use a local mock OIDC issuer to validate PKCE, state/nonce, token exchange, cookie attributes, proxy credential injection and cross-origin mutation rejection. The actual provider handshake must still be tested in staging; build green alone does not prove provider configuration correctness.

## Limits

- The selected identity provider is not configured in this repository and no cloud services have been provisioned.
- Refresh tokens are intentionally not stored; when the API access token expires, the user signs in again.
- HttpOnly cookies reduce token extraction but do not prevent CSRF/XSS on their own; same-origin mutation checks, CSP, dependency review and security testing remain necessary.
- The public content APIs continue to work without a session and expose only approved public records.
