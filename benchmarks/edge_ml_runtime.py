#!/usr/bin/env python3
"""Edge-ML runtime benchmark to estimate on-device readiness."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "docs" / "perf" / "results"


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    idx = int((len(values) - 1) * p)
    return sorted(values)[idx]


def main() -> int:
    rng = np.random.default_rng(21)
    X = rng.normal(size=(12000, 9)).astype(np.float32)
    y = (X[:, 0] + 0.5 * X[:, 1] - 0.25 * X[:, 2] > 0.3).astype(int)

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = LogisticRegression(max_iter=300, solver="lbfgs")
    model.fit(Xs, y)

    latencies_ms: list[float] = []
    batch = Xs[:10000]
    started = time.perf_counter()
    for i in range(len(batch)):
        t0 = time.perf_counter()
        _ = model.predict_proba(batch[i : i + 1])[0, 1]
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
    elapsed = max(time.perf_counter() - started, 1e-6)

    rps = len(batch) / elapsed
    p50 = percentile(latencies_ms, 0.50)
    p95 = percentile(latencies_ms, 0.95)
    p99 = percentile(latencies_ms, 0.99)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_model": "logistic_regression_optimized",
        "samples": len(batch),
        "throughput_inferences_per_second": round(float(rps), 2),
        "latency_ms": {
            "p50": round(float(p50), 4),
            "p95": round(float(p95), 4),
            "p99": round(float(p99), 4),
        },
        "targets": {
            "p95_under_ms": 5.0,
            "throughput_over_ips": 3000.0,
        },
        "target_met": p95 <= 5.0 and rps >= 3000.0,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"edge-ml-runtime-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"\nSaved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
