# Phase 15 — One-command local preview

## Goal

Make the actual Next.js `/demo` route easy to preview before running the whole application stack or configuring deployment.

## Requirements

- Node.js 20 or newer and npm.
- Network access only for the first run if frontend npm dependencies are not already installed.
- No Docker, PostgreSQL/PostGIS, Redis, API credentials, OIDC tenant, map-provider URL, live data feed, or cloud account is required for this UI route.

## Run

From the repository root:

```bash
bash scripts/start-interactive-demo.sh
```

Open `http://127.0.0.1:3000/demo` in a browser. The script installs the frontend dependencies if Next.js is not installed yet, then starts the Next.js development server on loopback. Stop it with Ctrl+C.

To use a different local port:

```bash
MCHO_DEMO_PORT=3001 bash scripts/start-interactive-demo.sh
```

The optional port must be an integer between 1024 and 65535.

## Data and safety

The `/demo` route is self-contained and uses synthetic fixtures. It does not fetch from `/api`, perform real review/publication writes, or connect to an external feed. Its map-like graphic is illustrative rather than geospatial evidence. Use the normal Docker Compose guide separately when you need to test the API, PostGIS schema, Redis queue, worker, or analyst workflow.

## Acceptance checks

1. Script fails with an actionable message when Node.js/npm is missing or too old.
2. Script validates the optional port before launch.
3. Script installs web dependencies only when the Next executable is missing.
4. The server binds to 127.0.0.1 and prints the exact preview URL.
5. Ctrl+C stops the development server.
6. Preview data remain clearly labeled as synthetic; no production services are provisioned.
