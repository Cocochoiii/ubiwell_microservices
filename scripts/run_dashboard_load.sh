#!/usr/bin/env bash
set -euo pipefail

mkdir -p docs/perf/results
k6 run k6/dashboard-report.js --summary-export docs/perf/results/k6-dashboard-summary.json
echo "Saved load summary to docs/perf/results/k6-dashboard-summary.json"
