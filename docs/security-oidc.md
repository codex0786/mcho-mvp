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
- There is no reviewer login screen or analyst workspace yet; these are a separate frontend implementation step.
- The Render Blueprint deliberately does not invent an issuer, client or secret. Add the three trusted OIDC values directly to the `mcho-api` environment after selecting the provider.
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
- [ ] Frontend login/token handling is implemented before exposing a review workspace.
