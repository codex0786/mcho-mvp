#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

for tool in docker python3 curl; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Error: $tool is required for the full local stack." >&2
    exit 1
  fi
done

if ! docker compose version >/dev/null 2>&1; then
  echo "Error: Docker Compose v2 is required. Install or update Docker Desktop, then retry." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Error: the Docker engine is not running. Start Docker Desktop and retry." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  python3 - .env <<'PY'
from pathlib import Path
import secrets
import sys

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
password = secrets.token_hex(32)
found = False
for index, line in enumerate(lines):
    if line.startswith("POSTGRES_PASSWORD="):
        lines[index] = f"POSTGRES_PASSWORD={password}"
        found = True
        break
if not found:
    raise SystemExit("Could not find POSTGRES_PASSWORD in .env.example; no stack started.")
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
path.chmod(0o600)
PY
  echo "Created .env with a generated local database password (kept out of Git)."
fi

python3 - .env <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
password = None
for line in path.read_text(encoding="utf-8").splitlines():
    if line.startswith("POSTGRES_PASSWORD="):
        password = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
if not password or password == "change-this-local-password":
    raise SystemExit(
        "Error: .env has an empty/default POSTGRES_PASSWORD. "
        "Set a strong local password and rerun; the existing file was not overwritten."
    )
PY

wait_for_url() {
  local label="$1"
  local url="$2"
  local service="$3"
  echo "Waiting for ${label}..."
  for attempt in {1..60}; do
    if curl --silent --fail --max-time 3 "$url" >/dev/null 2>&1; then
      echo "PASS ${label}"
      return 0
    fi
    sleep 2
  done
  echo "FAIL ${label}: ${url} did not become healthy." >&2
  docker compose ps >&2 || true
  docker compose logs --tail=80 "$service" >&2 || true
  return 1
}

echo "Starting MCHO local dependencies..."
docker compose up -d db redis
echo "Applying database migrations..."
docker compose run --build --rm api alembic upgrade head
echo "Building and starting MCHO API, worker and web..."
docker compose up --build -d api worker web

wait_for_url "API readiness (database/PostGIS/Redis)" "http://127.0.0.1:8000/api/v1/health/ready" api
echo "Ensuring only unpublished synthetic demo fixtures exist..."
docker compose exec -T api python -m app.seed_demo
wait_for_url "web prototype" "http://127.0.0.1:3000/demo" web

echo "Running API and same-origin proxy smoke tests..."
bash scripts/smoke-test.sh

echo ""
echo "MCHO local stack is ready."
echo "Prototype:         http://127.0.0.1:3000/demo"
echo "Application:       http://127.0.0.1:3000/"
echo "API documentation: http://127.0.0.1:8000/docs"
echo "Analyst workspace: http://127.0.0.1:3000/analyst (OIDC must be configured for sign-in)."
echo "All live connectors remain disabled unless separately configured and approved."
echo "Stop the stack with: docker compose down"
echo "This preserves local database volumes. Deleting data requires an explicit separate decision."
