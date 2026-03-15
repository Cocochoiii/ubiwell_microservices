#!/usr/bin/env python3
"""Generate SLO/error-budget markdown from benchmark + k6 summary artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "docs" / "perf" / "results"
REPORT_FILE = ROOT / "docs" / "perf" / "SLO_REPORT.md"


def latest(pattern: str) -> Path | None:
    files = sorted(RESULTS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def read_json(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text())


def k6_metrics(k6_data: dict) -> tuple[float, float]:
    metrics = k6_data.get("metrics", {})
    p95 = metrics.get("http_req_duration", {}).get("p(95)", 0.0)
    fail_rate = metrics.get("http_req_failed", {}).get("value", 1.0)
    return float(p95), float(fail_rate)


def main() -> int:
    bench_path = latest("benchmark-*.json")
    k6_path = latest("k6-dashboard-summary.json")
    bench = read_json(bench_path)
    k6 = read_json(k6_path)
    p95, fail_rate = k6_metrics(k6)

    target_p95_ms = 350.0
    target_fail_rate = 0.001
    slo_ok = p95 <= target_p95_ms and fail_rate <= target_fail_rate

    content = f"""# SLO Report

Generated at: `{datetime.now(timezone.utc).isoformat()}`

## SLO Targets

- Report/read API p95 latency: `< {target_p95_ms} ms`
- HTTP error rate: `< {target_fail_rate}`
- Report optimization improvement: `>= 85%`

## Current Results

- Benchmark file: `{bench_path.name if bench_path else "missing"}`
- k6 summary file: `{k6_path.name if k6_path else "missing"}`

- Improvement percent: `{bench.get("improvement_percent", 0):.2f}%`
- Improvement target met: `{bench.get("target_met_85_percent", False)}`
- k6 p95 latency: `{p95:.2f} ms`
- k6 error rate: `{fail_rate:.6f}`
- SLO overall status: `{"PASS" if slo_ok else "FAIL"}`

## Error Budget View

- Allowed failure ratio per request: `{target_fail_rate}`
- Observed failure ratio: `{fail_rate:.6f}`
- Burn ratio (observed / allowed): `{(fail_rate / target_fail_rate) if target_fail_rate > 0 else 0:.2f}`

## Evidence

- `docs/perf/results/`
- `docs/perf/screenshots/`
- `docs/perf/INTERVIEW_DEMO_REPORT.md`
"""

    REPORT_FILE.write_text(content)
    print(f"Generated {REPORT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
