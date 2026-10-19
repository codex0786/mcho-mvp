# Free-tier deployment (Vercel + Render + Neon + Upstash)

This guide puts the public MCHO API and its PostGIS database online at no cost,
behind the existing Vercel frontend. It uses four free accounts. No credit card
should be added to any of them: on several providers, adding a card silently
moves you to pay-as-you-go.

| Piece | Provider (free plan) | Created by |
|---|---|---|
| Web (`apps/web`) | Vercel Hobby, project `mcho-mvp` | Already live at <https://mcho-mvp.vercel.app> |
| API (`services/api`) | Render free web service `mcho-api` | `render.yaml` Blueprint |
| PostgreSQL + PostGIS | Neon free | You, in the Neon console |
| Redis | Upstash free | You, in the Upstash console |

Put everything in **US East (N. Virginia, AWS `us-east-1`)**. Vercel's functions
run there by default, so every hop stays in one region.

## What you get, and what you don't

Works:
- Public read API on a real PostGIS database: `/api/v1/health/*`, `/events`, `/events/{id}`, `/events/{id}/evidence`, `/map/events`, `/sources`.
- The home page map and evidence list call the API through the Vercel proxy at `/api/backend`.
- Migrations run automatically on every API start.

Does not work yet (by design, fails closed):
- **Sign-in.** There is no identity provider yet, so `/analyst` and all reviewer, publisher and admin endpoints return 503.
- **Ingestion.** There is no Celery worker, because Render has no free background workers and a polling worker would exhaust Upstash's free quota. "Queue run" returns 503.
- **Data.** The database starts empty, and public endpoints return empty lists until events are reviewed and published through the analyst workflow, which needs sign-in.

Free-tier behaviour to expect:
- The API sleeps after **15 minutes** without traffic, and the next request takes **about a minute** to wake it ([Render](https://render.com/docs/free)). The first map load after a quiet period can show "Map data unavailable"; press **Refresh map data** after a minute.
- Render gives 750 free instance hours per month; one always-on service uses at most about 744.
- Neon's free plan has a small per-project storage allowance and a monthly compute cap; compute suspends until the next month if exceeded ([Neon](https://neon.com/docs/introduction/plans)).
- Upstash allows 500,000 commands per month ([Upstash](https://upstash.com/docs/redis/overall/pricing)). Without a worker, the API only uses Redis for readiness checks.

## 1. Neon — PostgreSQL with PostGIS

1. Sign up at <https://neon.com> and create a project:
   - **Postgres version:** 17 (the version CI tests against).
   - **Region:** AWS US East 1 (N. Virginia).
2. On the project dashboard, open **Connect**:
   - Turn **Connection pooling off**. MCHO needs the *direct* connection: Alembic and psycopg's prepared statements are not suited to a transaction-mode pooler, and a single small API doesn't need pooling.
   - Copy the connection string. It looks like
     `postgresql://neondb_owner:PASSWORD@ep-xxxx.us-east-1.aws.neon.tech/neondb?sslmode=require`.
     Keep `sslmode=require`; the API keeps query parameters and switches to the psycopg driver itself.
3. You don't need to enable PostGIS by hand: the first migration runs `CREATE EXTENSION IF NOT EXISTS postgis`. If the API log later shows a permission error there, run `CREATE EXTENSION postgis;` once in Neon's SQL editor.

## 2. Upstash — Redis

1. Sign up at <https://upstash.com> and create a **Redis** database:
   - **Region:** AWS us-east-1.
   - **TLS:** enabled (the default).
2. Copy the Redis URL that starts with `rediss://` (two s's) and add
   `?ssl_cert_reqs=required` to the end:
   `rediss://default:PASSWORD@xxxx.upstash.io:6379?ssl_cert_reqs=required`.
   Celery expects this parameter on `rediss://` URLs (its Redis result backend rejects them without it), and it keeps certificate verification on.

## 3. Render — the API

1. Sign up at <https://render.com> with GitHub and give Render access to `codex0786/mcho-mvp`.
2. Click **New → Blueprint**, select the repository and branch `main`. Render reads `render.yaml` and proposes **one free web service, `mcho-api`**. If it proposes anything else, or anything with a price, stop: you have selected the paid file in `deploy/`.
3. When asked for values, paste:
   - `DATABASE_URL` = the Neon string from step 1
   - `REDIS_URL` = the Upstash string from step 2
4. Click **Apply**. The first build takes a few minutes. When it finishes, note the service URL, normally `https://mcho-api.onrender.com`; Render adds a suffix if the name is taken.
5. Check it from a terminal (the first call may take a minute):

   ```bash
   curl -s https://mcho-api.onrender.com/api/v1/health/ready
   ```

   Expected: `{"status":"ready","dependencies":{"database":"ok","postgis":"ok","redis":"ok"}}`.

## 4. Vercel — point the web app at the API

In the Vercel project **mcho-mvp → Settings → Environment Variables**, add these for **Production**:

| Name | Value |
|---|---|
| `MCHO_API_ORIGIN` | the Render URL, e.g. `https://mcho-api.onrender.com` (no path, no trailing slash) |
| `MCHO_WEB_ORIGIN` | `https://mcho-mvp.vercel.app` |
| `MCHO_MAP_STYLE_URL` | *optional* — a MapLibre style you are permitted to use, e.g. OpenFreeMap's `https://tiles.openfreemap.org/styles/liberty` (no key; check its terms first). Without it the map shows an explicit "no basemap" message. |

Then redeploy production (**Deployments → … → Redeploy**). These are runtime variables read by the proxy route, so they take effect without a code change.

## 5. Verify end to end

```bash
API_URL=https://mcho-api.onrender.com WEB_URL=https://mcho-mvp.vercel.app WAIT_FOR_API_SECONDS=120 bash scripts/smoke-test.sh
```

All checks should print `PASS`. Then open <https://mcho-mvp.vercel.app>: the map status should read "0 published map features · API data timestamp …" rather than "Backend API origin is not configured".

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Render deploy fails at `alembic upgrade head` | Wrong `DATABASE_URL` (check you copied the direct, non-pooled string), or Neon compute is suspended for the month. The API log shows the error type but never the password. |
| `/health/ready` says `redis: unavailable` | `REDIS_URL` must start with `rediss://`; check the password and that the Upstash database still exists. |
| Home page says "Backend API origin is not configured" | `MCHO_API_ORIGIN` is missing on Vercel, or production wasn't redeployed after adding it. |
| Home page shows HTTP 502 | The API was asleep and the proxy's 20-second timeout passed first. Wait a minute and press Refresh. |
| All free Render services stop mid-month | The 750 free hours ran out; they resume on the 1st. |

## Moving off the free tier

`deploy/render-paid-pilot.yaml` describes a paid pilot with a Celery worker, Render Postgres and Key Value, and a pre-deploy migration step. Review current pricing before applying it; it creates billable resources.
