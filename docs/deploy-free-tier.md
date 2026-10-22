# Free-tier deployment (Vercel + Render + Neon)

This guide puts the public MCHO API and its PostGIS database online at no cost,
behind the existing Vercel frontend. It uses three free accounts. No credit card
should be added to any of them: on several providers, adding a card silently
moves you to pay-as-you-go.

| Piece | Provider (free plan) | Created by |
|---|---|---|
| Web (`apps/web`) | Vercel Hobby, project `mcho-mvp` | Already live at <https://mcho-mvp.vercel.app> |
| API (`services/api`) | Render free web service `mcho-api` | `render.yaml` Blueprint |
| PostgreSQL + PostGIS | Neon free | You, in the Neon console |
| Redis | Not used (no worker on the free tier) | — |

Put everything in **US East (N. Virginia, AWS `us-east-1`)**. Vercel's functions
run there by default, so every hop stays in one region.

## What you get, and what you don't

Works:
- Public read API on a real PostGIS database: `/api/v1/health/*`, `/events`, `/events/{id}`, `/events/{id}/evidence`, `/map/events`, `/sources`.
- The home page map and evidence list call the API through the Vercel proxy at `/api/backend`.
- Migrations run automatically on every API start.

Does not work yet (by design, fails closed):
- **Sign-in.** There is no identity provider yet, so `/analyst` and all reviewer, publisher and admin endpoints return 503.
- **Ingestion.** There is no Celery worker, because Render has no free background workers. "Queue run" returns 503.
- **Data.** The database starts empty, and public endpoints return empty lists until events are reviewed and published through the analyst workflow, which needs sign-in.

Free-tier behaviour to expect:
- The API sleeps after **15 minutes** without traffic, and the next request takes **about a minute** to wake it ([Render](https://render.com/docs/free)). The first map load after a quiet period can show "Map data unavailable"; press **Refresh map data** after a minute.
- Render gives 750 free instance hours per month; one always-on service uses at most about 744.
- Neon's free plan has a small per-project storage allowance and a monthly compute cap; compute suspends until the next month if exceeded ([Neon](https://neon.com/docs/introduction/plans)).
- No Redis: `REDIS_REQUIRED=false`, so readiness reports Redis as `disabled`. Add Redis (e.g. Upstash) only together with a Celery worker.

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

## 2. Redis (not needed)

The free setup has no Celery worker, so it doesn't use Redis. The Blueprint sets `REDIS_REQUIRED=false`. If you add a worker later, create a Redis database (e.g. Upstash, with a `rediss://…?ssl_cert_reqs=required` URL), set `REDIS_URL`, and set `REDIS_REQUIRED=true`.

## 3. Render — the API

1. Sign up at <https://render.com> with GitHub and give Render access to `codex0786/mcho-mvp`.
2. Click **New → Blueprint**, select the repository and branch `main`. Render reads `render.yaml` and proposes **one free web service, `mcho-api`**. If it proposes anything else, or anything with a price, stop: you have selected the paid file in `deploy/`.
3. When asked for values, paste:
   - `DATABASE_URL` = the Neon string from step 1
   - `NASA_FIRMS_API_KEY` = your FIRMS MAP_KEY (see [satellite-thermal.md](./satellite-thermal.md))
4. Click **Apply**. The first build takes a few minutes. When it finishes, note the service URL, normally `https://mcho-api.onrender.com`; Render adds a suffix if the name is taken.
5. Check it from a terminal (the first call may take a minute):

   ```bash
   curl -s https://mcho-api.onrender.com/api/v1/health/ready
   ```

   Expected: `{"status":"ready","dependencies":{"database":"ok","postgis":"ok","redis":"disabled"}}`.

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
| `/health/ready` says `redis: unavailable` | `REDIS_REQUIRED` is true without a working Redis. On the free tier set `REDIS_REQUIRED=false`. |
| Home page says "Backend API origin is not configured" | `MCHO_API_ORIGIN` is missing on Vercel, or production wasn't redeployed after adding it. |
| Home page shows HTTP 502 | The API was asleep and the proxy's 20-second timeout passed first. Wait a minute and press Refresh. |
| All free Render services stop mid-month | The 750 free hours ran out; they resume on the 1st. |

## Moving off the free tier

`deploy/render-paid-pilot.yaml` describes a paid pilot with a Celery worker, Render Postgres and Key Value, and a pre-deploy migration step. Review current pricing before applying it; it creates billable resources.

## Keeping the API awake

Render's free web services sleep after 15 minutes without traffic. Waking takes about a minute and occasionally fails
(`hibernate-wake-error`), which leaves visitors waiting.

**How the API stays awake:**

- **Self-ping:** the API requests its own public health URL every 10 minutes (`app/core/keep_warm.py`). It uses
  `RENDER_EXTERNAL_URL`, which Render sets automatically, so there is nothing to configure.
  - Set `KEEP_WARM_MINUTES=0` to turn it off.
  - Set `KEEP_WARM_URL` to use a different public URL.
- **Backup:** `.github/workflows/keep-warm.yml` pings every 10 minutes and wakes the service if it ever sleeps. GitHub
  delays scheduled runs, so the backup alone is not enough.

**Free-tier hours:**

- One service running all month uses at most 744 of the 750 free instance hours per workspace.
- If another free web service in the same Render workspace also runs, the hours run out before the month ends. Render
  then suspends free services until the next month.
