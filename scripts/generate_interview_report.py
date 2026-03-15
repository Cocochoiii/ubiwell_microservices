#!/usr/bin/env python3
"""Generate markdown interview/demo report from latest benchmark and screenshots."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "docs" / "perf" / "results"
SCREENSHOT_DIR = ROOT / "docs" / "perf" / "screenshots"
OUT_FILE = ROOT / "docs" / "perf" / "INTERVIEW_DEMO_REPORT.md"


def latest_benchmark() -> dict:
    files = sorted(BENCH_DIR.glob("benchmark-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return {}
    return json.loads(files[0].read_text())


def screenshot_line(name: str, filename: str) -> str:
    path = SCREENSHOT_DIR / filename
    if path.exists():
        return f"- {name}: `docs/perf/screenshots/{filename}`"
    return f"- {name}: (missing) run `make capture-screenshots`"


def build_report(bench: dict) -> str:
    now = datetime.now(timezone.utc).isoformat()
    improvement = bench.get("improvement_percent", 0.0)
    target_met = bench.get("target_met_85_percent", False)
    naive = bench.get("naive_avg_seconds", 0.0)
    optimized = bench.get("optimized_avg_seconds", 0.0)
    rounds = bench.get("rounds", "n/a")

    return f"""# UbiWell Interview Demo Report

Generated at: `{now}`

## Executive Summary

- Built and validated a production-style reporting platform with role-aware realtime dashboards.
- Demonstrated report optimization via multi-tier caching and algorithmic redesign.
- Collected reproducible operational evidence (benchmarks, load tests, observability screenshots, SLO report).

## Performance Summary

- Benchmark rounds: `{rounds}`
- Naive average: `{naive:.6f}s`
- Optimized average: `{optimized:.6f}s`
- Improvement: `{improvement:.2f}%`
- 85% target met: `{target_met}`

## Technical Highlights

- L1 in-memory cache in `report-service`
- L2 Redis cache with invalidation endpoint
- L3 precomputed Mongo aggregates
- role-based dashboard metadata templates (120 generated)
- websocket realtime stream with tenant-aware auth

## Evidence Artifacts

{screenshot_line("API docs", "api-docs.png")}
{screenshot_line("Web dashboard", "web-dashboard.png")}
{screenshot_line("Grafana overview", "grafana-overview.png")}
{screenshot_line("Prometheus", "prometheus.png")}
{screenshot_line("Jaeger", "jaeger.png")}

## Reproduce This Report

```bash
make demo-up
make test-backend
make bench-report
make load-dashboard
make e2e-flow
make capture-screenshots
make interview-report
```

## Resume Mapping

This demo supports claims around:
- report optimization using caching + algorithm design
- high-scale dashboard delivery with role-based access controls
- realtime operational visibility with production observability
"""


def main() -> int:
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    bench = latest_benchmark()
    OUT_FILE.write_text(build_report(bench))
    print(f"Generated report: {OUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
