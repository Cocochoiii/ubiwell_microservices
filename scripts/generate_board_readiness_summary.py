#!/usr/bin/env python3
"""Generate concise board/interview readiness summary from latest artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "docs" / "perf" / "results"
OUT = ROOT / "docs" / "perf" / "BOARD_READINESS_SUMMARY.md"


def latest(pattern: str) -> Path | None:
    files = sorted(RESULTS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def read_json(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    gate = read_json(RESULTS_DIR / "release-gate-report.json")
    quality = read_json(RESULTS_DIR / "quality-engineering-metrics.json")
    dep = read_json(RESULTS_DIR / "dependency-vuln-scan.json")
    pipeline = read_json(latest("pipeline-throughput-*.json"))
    loss = read_json(latest("data-loss-reduction-*.json"))
    ios = read_json(latest("ios-edge-reliability-*.json"))
    bench = read_json(latest("benchmark-*.json"))
    k6 = read_json(RESULTS_DIR / "k6-dashboard-summary.json")

    p95 = float(k6.get("metrics", {}).get("http_req_duration", {}).get("p(95)", 0.0))
    fail_rate = float(k6.get("metrics", {}).get("http_req_failed", {}).get("value", 1.0))
    strict_pass = bool(gate.get("strict_mode")) and bool(gate.get("gate_passed"))

    lines = [
        "# Board Readiness Summary",
        "",
        f"Generated at: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "## Executive Status",
        "",
        f"- Strict release gate: **{'PASS' if strict_pass else 'CHECK REQUIRED'}**",
        f"- Dependency vulnerabilities: **{dep.get('total_vulnerabilities', 'N/A')}**",
        f"- Quality coverage: **{quality.get('combined_coverage_percent', 'N/A')}%** (target 92%+)",
        f"- Total authored tests: **{quality.get('total_tests', 'N/A')}**",
        "",
        "## KPI Snapshot",
        "",
        f"- Report optimization improvement: **{bench.get('improvement_percent', 0):.2f}%**",
        f"- Dashboard API p95 latency: **{p95:.2f} ms**",
        f"- Dashboard API error rate: **{fail_rate:.6f}**",
        f"- Pipeline peak throughput: **{pipeline.get('peak_events_per_second', 'N/A')} events/s**",
        f"- Pipeline loss reduction: **{loss.get('loss_reduction_percentage_points', 'N/A')} percentage points**",
        f"- iOS edge reliability: **{ios.get('reliability', 'N/A')}** on **{ios.get('total_daily_sensor_readings', 'N/A')} readings/day**",
        f"- iOS estimated monthly cloud savings: **${ios.get('estimated_monthly_savings_usd', 'N/A')}**",
        "",
        "## Primary Evidence",
        "",
        "- `docs/perf/RELEASE_READINESS_REPORT.md`",
        "- `docs/perf/QUALITY_ENGINEERING_REPORT.md`",
        "- `docs/perf/DEPENDENCY_VULN_REPORT.md`",
        "- `docs/perf/SLO_REPORT.md`",
        "- `docs/perf/IOS_EDGE_REPORT.md`",
        "- `docs/perf/PIPELINE_PRODUCTION_REPORT.md`",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
