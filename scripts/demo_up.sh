#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

echo "Starting stack..."
docker compose up --build -d

echo "Waiting for API gateway..."
for _ in {1..60}; do
  if curl -sf "http://localhost:8000/healthz" >/dev/null; then
    break
  fi
  sleep 2
done

curl -sf "http://localhost:8000/healthz" >/dev/null
echo "Gateway healthy."

echo "Seeding demo data..."
python3 scripts/seed_demo_data.py

echo
echo "Demo ready:"
echo "  API Gateway: http://localhost:8000"
echo "  Web Dashboard: http://localhost:5173"
echo "  Prometheus:  http://localhost:9090"
echo "  Grafana:     http://localhost:3000 (admin/admin)"
echo "  Jaeger:      http://localhost:16686"
