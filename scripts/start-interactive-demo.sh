#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="$ROOT_DIR/apps/web"
PORT="${MCHO_DEMO_PORT:-3000}"

if ! command -v node >/dev/null 2>&1; then
  echo "Error: Node.js is required. Install Node.js 20 or newer, then rerun this command." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm is required. Install it with Node.js 20 or newer." >&2
  exit 1
fi

NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])')"
if (( NODE_MAJOR < 20 )); then
  echo "Error: MCHO local preview requires Node.js 20 or newer; detected $(node --version)." >&2
  exit 1
fi

if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1024 || PORT > 65535 )); then
  echo "Error: MCHO_DEMO_PORT must be an integer between 1024 and 65535." >&2
  exit 1
fi

if [[ ! -x "$WEB_DIR/node_modules/.bin/next" ]]; then
  echo "Installing MCHO frontend dependencies (first run only)... "
  (cd "$WEB_DIR" && npm install --no-audit --no-fund)
fi

echo ""
echo "MCHO interactive prototype"
echo "Open: http://127.0.0.1:${PORT}/demo"
echo "This preview uses fictional fixtures only and does not start the API, database, Redis, worker, or live data connectors."
echo "Press Ctrl+C to stop the development server."
echo ""
cd "$WEB_DIR"
exec npm run dev -- --hostname 127.0.0.1 --port "$PORT"
