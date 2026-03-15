#!/usr/bin/env bash
set -euo pipefail

SERVICE="${1:-participant-service}"
DURATION_SECONDS="${2:-30}"
HEALTH_URL="${3:-http://localhost:8000/healthz}"

echo "Starting chaos test against service=${SERVICE} duration=${DURATION_SECONDS}s"
docker compose stop "${SERVICE}"
sleep "${DURATION_SECONDS}"
docker compose start "${SERVICE}"
sleep 5

echo "Checking gateway health after chaos event..."
curl -sS "${HEALTH_URL}" || {
  echo "Health check failed after chaos test" >&2
  exit 1
}

echo
echo "Chaos test complete."
