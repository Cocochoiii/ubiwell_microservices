#!/usr/bin/env python3
"""Release readiness gate for portfolio-grade production evidence."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "docs" / "perf" / "results"
REPORT_JSON = RESULTS_DIR / "release-gate-report.json"
REPORT_MD = ROOT / "docs" / "perf" / "RELEASE_READINESS_REPORT.md"


@dataclass
class CheckResult:
    name: str
    passed: bool
    details: str
    required: bool = True


def latest(pattern: str) -> Path | None:
    files = sorted(RESULTS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def read_json(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def check_report_optimization() -> CheckResult:
    bench_path = latest("benchmark-*.json")
    if not bench_path:
        return CheckResult("report_optimization", False, "Missing benchmark artifact")
    payload = read_json(bench_path)
    improvement = float(payload.get("improvement_percent", 0.0))
    passed = improvement >= 85.0
    return CheckResult(
        "report_optimization",
        passed,
        f"improvement={improvement:.2f}% (target >= 85%), file={bench_path.name}",
    )


def check_slo() -> CheckResult:
    k6_path = latest("k6-dashboard-summary.json")
    if not k6_path:
        return CheckResult("slo_dashboard_api", False, "Missing k6 dashboard summary")
    payload = read_json(k6_path).get("metrics", {})
    p95 = float(payload.get("http_req_duration", {}).get("p(95)", 0.0))
    fail_rate = float(payload.get("http_req_failed", {}).get("value", 1.0))
    passed = p95 <= 350.0 and fail_rate <= 0.001
    return CheckResult(
        "slo_dashboard_api",
        passed,
        f"p95={p95:.2f}ms (<=350), error_rate={fail_rate:.6f} (<=0.001), file={k6_path.name}",
    )


def check_quality() -> CheckResult:
    quality_path = RESULTS_DIR / "quality-engineering-metrics.json"
    if not quality_path.exists():
        return CheckResult("quality_engineering", False, "Missing quality metrics artifact")
    payload = read_json(quality_path)
    tests = int(payload.get("total_tests", 0))
    coverage = float(payload.get("combined_coverage_percent", 0.0))
    bug_reduction = float(payload.get("bug_reduction_percent", 0.0))
    hours = float(payload.get("hours_saved_per_week", 0.0))
    passed = tests >= 200 and coverage >= 92.0 and bug_reduction >= 80.0 and hours >= 20.0
    return CheckResult(
        "quality_engineering",
        passed,
        (
            f"tests={tests} (>=200), coverage={coverage:.2f}% (>=92), "
            f"bug_reduction={bug_reduction:.2f}% (>=80), hours_saved={hours:.1f} (>=20)"
        ),
    )


def check_ios_edge() -> CheckResult:
    ios_path = latest("ios-edge-reliability-*.json")
    if not ios_path:
        return CheckResult("ios_edge_module", False, "Missing iOS edge reliability artifact")
    payload = read_json(ios_path)
    readings = int(payload.get("total_daily_sensor_readings", 0))
    reliability = float(payload.get("reliability", 0.0))
    savings = float(payload.get("estimated_monthly_savings_usd", 0.0))
    passed = readings >= 10000 and reliability >= 0.997 and savings >= 3000.0
    return CheckResult(
        "ios_edge_module",
        passed,
        f"readings={readings} (>=10000), reliability={reliability:.4f} (>=0.997), savings=${savings:.2f} (>=3000)",
    )


def check_pipeline(strict: bool) -> CheckResult:
    throughput_path = latest("pipeline-throughput-*.json")
    loss_path = latest("data-loss-reduction-*.json")
    required = strict
    if not throughput_path or not loss_path:
        return CheckResult(
            "fault_tolerant_pipeline",
            False if required else True,
            (
                "Missing pipeline evidence artifacts. "
                "Run make bench-pipeline-throughput && make bench-data-loss."
            ),
            required=required,
        )

    throughput = read_json(throughput_path)
    loss = read_json(loss_path)
    target_met = bool(throughput.get("target_met", False))
    reduction = float(loss.get("loss_reduction_percentage_points", 0.0))
    passed = target_met and reduction >= 15.0
    return CheckResult(
        "fault_tolerant_pipeline",
        passed,
        (
            f"throughput_target_met={target_met}, loss_reduction={reduction:.2f}pp (>=15), "
            f"files={throughput_path.name},{loss_path.name}"
        ),
        required=required,
    )


def check_security_artifacts(strict: bool) -> CheckResult:
    required = strict
    required_files = [
        RESULTS_DIR / "dependency-vuln-scan.json",
        RESULTS_DIR / "secret-scan.json",
        RESULTS_DIR / "container-scan.json",
        RESULTS_DIR / "sbom.cdx.json",
        RESULTS_DIR / "release-checklist-signature.json",
    ]
    missing = [f.name for f in required_files if not f.exists()]
    if missing:
        return CheckResult(
            "security_compliance_artifacts",
            False if required else True,
            f"Missing: {', '.join(missing)}. Run make security-compliance.",
            required=required,
        )
    return CheckResult(
        "security_compliance_artifacts",
        True,
        "All security/compliance artifacts are present.",
        required=required,
    )


def write_reports(results: list[CheckResult], strict: bool) -> None:
    required_results = [r for r in results if r.required]
    gate_passed = all(r.passed for r in required_results)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strict_mode": strict,
        "gate_passed": gate_passed,
        "results": [
            {
                "name": r.name,
                "passed": r.passed,
                "required": r.required,
                "details": r.details,
            }
            for r in results
        ],
    }
    REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    status = "PASS" if gate_passed else "FAIL"
    lines = [
        "# Release Readiness Report",
        "",
        f"Generated at: `{payload['generated_at']}`",
        f"Strict mode: `{strict}`",
        f"Overall gate: **{status}**",
        "",
        "## Checklist",
        "",
    ]
    for r in results:
        flag = "required" if r.required else "advisory"
        icon = "PASS" if r.passed else "FAIL"
        lines.append(f"- `{r.name}` [{flag}] -> **{icon}**: {r.details}")
    lines.extend(
        [
            "",
            "## Reproduce",
            "",
            "```bash",
            "make release-gate",
            "make release-gate-strict",
            "```",
        ]
    )
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate production-readiness evidence.")
    parser.add_argument("--strict", action="store_true", help="Require pipeline throughput/loss artifacts")
    args = parser.parse_args()

    results = [
        check_report_optimization(),
        check_slo(),
        check_quality(),
        check_ios_edge(),
        check_pipeline(strict=args.strict),
        check_security_artifacts(strict=args.strict),
    ]
    write_reports(results, strict=args.strict)

    required_results = [r for r in results if r.required]
    return 0 if all(r.passed for r in required_results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
