# Sign-in with Auth0 (free plan)

This turns on the analyst workspace at <https://mcho-mvp.vercel.app/analyst>:
source review, event drafting, the review queue, publication and the admin source
registry. It uses a free Auth0 tenant. Nothing here needs a credit card.

How it fits together:

- The **web app** (Vercel) signs people in with Authorization Code + PKCE on the
  server. It keeps the access token in an HttpOnly cookie, so browser JavaScript
  never sees it.
- The **API** (Render) checks each access token's signature, issuer, audience and
  expiry against Auth0, then reads the person's roles from the
  `https://mcho.app/roles` claim.
- **Roles** are managed in Auth0 and decide what each person can do:

| Role | Can |
|---|---|
| `analyst` | Read source documents, create event drafts |
| `reviewer` | Analyst actions, plus record review decisions |
| `publisher` | Read the review queue, publish approved events, issue corrections |
| `admin` | Everything, plus manage sources and queue ingestion runs |

Publishing requires **three different people**: the editor who wrote the
version, an independent reviewer, and a separate publisher. To try the full
flow end to end you need at least three accounts.

## 1. Create the tenant

1. Sign up at <https://auth0.com/signup>.
2. Create a tenant in a **US** region. Its domain looks like
   `mcho-dev.us.auth0.com`; this guide calls it `TENANT_DOMAIN`.

## 2. Register the API

**Applications → APIs → Create API**

| Field | Value |
|---|---|
| Name | `MCHO API` |
| Identifier | `https://api.mcho.app` (a name, not a URL Auth0 will call; it cannot be changed later) |
| Signing algorithm | `RS256` |

## 3. Register the web app

**Applications → Applications → Create Application → Single Page Web Application**, named `MCHO Web`.

Choose "Single Page" because the web server exchanges the code with PKCE and no
client secret. In its **Settings**, fill in:

| Field | Value |
|---|---|
| Allowed Callback URLs | `https://mcho-mvp.vercel.app/api/auth/callback` |
| Allowed Logout URLs | `https://mcho-mvp.vercel.app/analyst` |
| Allowed Web Origins | `https://mcho-mvp.vercel.app` |

Save, and note the **Client ID**. It is a public identifier, not a secret.

## 4. Create roles and users

1. **User Management → Roles**: create `analyst`, `reviewer`, `publisher`, `admin`.
2. **User Management → Users**: create (or invite) the people who will use it.
   Open each user, choose **Roles → Assign roles**, and assign at least one role.
   For a full test, use three users: an *analyst* who drafts, a *reviewer* who
   reviews, and a *publisher* who publishes. Give yourself `admin` as well.

If your Auth0 plan doesn't offer Roles, put the roles on each user instead, under
**User → app_metadata**: `{ "mcho_roles": ["reviewer"] }`. The Action below reads either.

## 5. Put roles into the access token

**Actions → Library → Create Action → Build from scratch**: name it `MCHO roles`, trigger **Login / Post Login**. Paste:

```js
exports.onExecutePostLogin = async (event, api) => {
  const fromRbac = (event.authorization && event.authorization.roles) || [];
  const fromMetadata = (event.user.app_metadata && event.user.app_metadata.mcho_roles) || [];
  const roles = [...new Set([...fromRbac, ...fromMetadata])];
  api.accessToken.setCustomClaim("https://mcho.app/roles", roles);
  api.idToken.setCustomClaim("https://mcho.app/roles", roles);
};
```

Click **Deploy**. Then go to **Actions → Triggers → post-login**, drag `MCHO roles`
into the flow, and click **Apply**.

## 6. Configure the API on Render

**Render → mcho-api → Environment**, add or edit:

| Name | Value |
|---|---|
| `OIDC_ISSUER` | `https://TENANT_DOMAIN/` — **with** the trailing slash |
| `OIDC_AUDIENCE` | `https://api.mcho.app` |
| `OIDC_JWKS_URL` | `https://TENANT_DOMAIN/.well-known/jwks.json` |
| `OIDC_ROLE_CLAIM` | `https://mcho.app/roles` |

Save. Render redeploys automatically.

## 7. Configure the web app on Vercel

**Vercel → mcho-mvp → Settings → Environment Variables (Production)**:

| Name | Value |
|---|---|
| `MCHO_OIDC_AUTHORITY` | `https://TENANT_DOMAIN` |
| `MCHO_OIDC_CLIENT_ID` | the Client ID from step 3 |
| `MCHO_OIDC_AUDIENCE` | `https://api.mcho.app` |

Leave `MCHO_OIDC_RESOURCE` empty. Then redeploy production.

## 8. Check it

1. Open <https://mcho-mvp.vercel.app/analyst> and click **Sign in securely**. You
   should land back on the workspace showing your roles.
2. `https://mcho-mvp.vercel.app/api/backend/api/v1/auth/me` (in the same
   browser) should return your subject and roles. It never returns a token.

| Symptom | Likely cause |
|---|---|
| "OIDC sign-in is not configured" | Vercel variables missing, or production not redeployed |
| Auth0 error "Callback URL mismatch" | Step 3 callback URL differs from `https://mcho-mvp.vercel.app/api/auth/callback` |
| Back on `/analyst?auth_error=token_exchange` | App type isn't Single Page, so Auth0 expects a client secret |
| Signed in, but API calls return 401 | `MCHO_OIDC_AUDIENCE` not set (Auth0 then issues an opaque token), or `OIDC_ISSUER` lacks the trailing slash |
| Signed in, but 403 on every action | No roles in the token: check role assignment and that the Action is in the post-login flow |
| API calls return 503 "not configured" | Render `OIDC_*` variables missing |

Notes:
- Sessions last up to one hour, then you sign in again.
- **Sign out** clears the MCHO session. Auth0 may still remember you, so the next
  sign-in can be instant.
