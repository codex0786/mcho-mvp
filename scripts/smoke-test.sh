#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
WEB_URL="${WEB_URL:-http://localhost:3000}"
API_URL="${API_URL%/}"
WEB_URL="${WEB_URL%/}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

fetch_json() {
  local name="$1"
  local url="$2"
  local output="$TMP_DIR/$name.json"
  local status
  status="$(curl --silent --show-error --max-time 20 --output "$output" --write-out '%{http_code}' "$url")" || {
    echo "FAIL $name: request failed: $url" >&2
    return 1
  }
  if [[ "$status" != "200" ]]; then
    echo "FAIL $name: HTTP $status from $url" >&2
    cat "$output" >&2 || true
    return 1
  fi
  echo "$output"
}

check_json() {
  local name="$1"
  local file="$2"
  local assertion="$3"
  if python3 - "$file" "$assertion" <<'PY'
import json
import sys

path, assertion = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)

checks = {
    "live": lambda x: x.get("status") == "alive",
    "ready": lambda x: x.get("status") == "ready"
        and x.get("dependencies", {}).get("database") == "ok"
        and x.get("dependencies", {}).get("postgis") == "ok",
    "events": lambda x: isinstance(x.get("items"), list)
        and "response_generated_at" in x,
    "map": lambda x: x.get("type") == "FeatureCollection"
        and isinstance(x.get("features"), list),
    "public_config": lambda x: all(key in x for key in (
        "oidcAuthority", "oidcClientId", "oidcResource", "mapStyleUrl"
    )),
}
if assertion not in checks or not checks[assertion](payload):
    raise SystemExit(1)
PY
  then
    echo "PASS $name"
  else
    echo "FAIL $name: response JSON contract was not satisfied" >&2
    return 1
  fi
}

live_file="$(fetch_json "api-live" "$API_URL/api/v1/health/live")"
check_json "API live" "$live_file" live

ready_file="$(fetch_json "api-ready" "$API_URL/api/v1/health/ready")"
check_json "API database/PostGIS readiness" "$ready_file" ready

events_file="$(fetch_json "api-events" "$API_URL/api/v1/events?page_size=1")"
check_json "published events contract" "$events_file" events

map_file="$(fetch_json "api-map" "$API_URL/api/v1/map/events?west=30&south=20&east=45&north=40")"
check_json "GeoJSON map contract" "$map_file" map

if curl --silent --show-error --fail --max-time 20 --output /dev/null "$WEB_URL/"; then
  echo "PASS web homepage"
else
  echo "FAIL web homepage: $WEB_URL/" >&2
  exit 1
fi

config_file="$(fetch_json "web-config" "$WEB_URL/api/public-config")"
check_json "web runtime configuration endpoint" "$config_file" public_config

proxy_file="$(fetch_json "web-api-proxy" "$WEB_URL/api/backend/api/v1/health/live")"
check_json "same-origin backend proxy" "$proxy_file" live

echo "Smoke tests passed. This confirms API/web wiring and service health only; it does not certify source licensing, data accuracy, authentication-provider policy, or operational fitness."
