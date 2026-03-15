#!/usr/bin/env python3
"""Generate advanced edge-ML readiness report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "docs" / "perf" / "results"
OUT = ROOT / "docs" / "perf" / "EDGE_ML_ADVANCED_REPORT.md"


def latest(pattern: str) -> Path | None:
    files = sorted(RESULTS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def read_json(path: Path | None) -> dict:
    if not path:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    metrics_path = RESULTS_DIR / "edge-ml-advanced-metrics.json"
    runtime_path = latest("edge-ml-runtime-*.json")
    metrics = read_json(metrics_path if metrics_path.exists() else None)
    runtime = read_json(runtime_path)

    content = f"""# Edge ML Advanced Report

Generated at: `{datetime.now(timezone.utc).isoformat()}`

## Model Quality

- Dataset size: **{metrics.get("sample_count", "N/A")}**
- Positive class rate: **{metrics.get("positive_rate", "N/A")}**
- Test ROC-AUC: **{metrics.get("test_roc_auc", "N/A")}**
- Test PR-AUC: **{metrics.get("test_pr_auc", "N/A")}**
- Test F1: **{metrics.get("test_f1", "N/A")}**
- Calibration ECE: **{metrics.get("test_ece", "N/A")}**

## Runtime Performance

- Throughput: **{runtime.get("throughput_inferences_per_second", "N/A")} inf/s**
- p50 latency: **{runtime.get("latency_ms", {}).get("p50", "N/A")} ms**
- p95 latency: **{runtime.get("latency_ms", {}).get("p95", "N/A")} ms**
- p99 latency: **{runtime.get("latency_ms", {}).get("p99", "N/A")} ms**
- Runtime target met: **{runtime.get("target_met", "N/A")}**

## Production Maturity Controls

- Calibrated classifier for probability reliability.
- Drift baseline exported for feature-distribution monitoring.
- Thresholded classification aligned to safety-oriented edge inference.

## Artifacts

- `{metrics_path.relative_to(ROOT).as_posix()}`
- `{runtime_path.relative_to(ROOT).as_posix() if runtime_path else "missing runtime artifact"}`
- `apps/ios-edge-module/Resources/tflite/advanced_scaler_drift_baseline.json`
"""
    OUT.write_text(content, encoding="utf-8")
    print(f"Generated: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
