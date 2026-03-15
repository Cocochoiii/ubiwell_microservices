#!/usr/bin/env python3
"""Edge-ML robustness benchmark: packet loss, sensor noise, and degradation tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "docs" / "perf" / "results"


def apply_packet_loss(X: np.ndarray, drop_pct: float, rng: np.random.Generator) -> np.ndarray:
    """Simulate packet loss: replace random feature values with NaN, then impute with column mean."""
    X_c = X.copy()
    n, d = X.shape
    n_drop = int(n * d * drop_pct / 100)
    for _ in range(n_drop):
        i, j = rng.integers(0, n), rng.integers(0, d)
        X_c[i, j] = np.nan
    col_mean = np.nanmean(X_c, axis=0)
    for j in range(d):
        mask = np.isnan(X_c[:, j])
        X_c[mask, j] = col_mean[j]
    return X_c


def apply_sensor_noise(X: np.ndarray, noise_std: float, rng: np.random.Generator) -> np.ndarray:
    """Add Gaussian sensor noise to simulate real-world measurement variability."""
    return X + rng.normal(0, noise_std, X.shape).astype(np.float32)


def apply_outlier_injection(X: np.ndarray, pct: float, rng: np.random.Generator) -> np.ndarray:
    """Inject outliers (spike noise) to simulate sensor glitches."""
    X_c = X.copy()
    n, d = X.shape
    n_out = int(n * pct / 100)
    for _ in range(n_out):
        i, j = rng.integers(0, n), rng.integers(0, d)
        X_c[i, j] += rng.choice([-1, 1]) * rng.uniform(3, 6) * np.std(X[:, j])
    return X_c


def main() -> int:
    rng = np.random.default_rng(42)
    n = 8000
    X = rng.normal(size=(n, 9)).astype(np.float32)
    y = (X[:, 0] + 0.5 * X[:, 1] - 0.25 * X[:, 2] > 0.3).astype(int)

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = LogisticRegression(max_iter=300, solver="lbfgs")
    model.fit(Xs, y)

    results: list[dict] = []

    # Baseline (no corruption)
    p = model.predict_proba(Xs)[:, 1]
    pred = (p >= 0.5).astype(int)
    baseline_f1 = float(f1_score(y, pred))
    baseline_auc = float(roc_auc_score(y, p))
    results.append(
        {"scenario": "baseline", "params": {}, "f1": round(baseline_f1, 4), "roc_auc": round(baseline_auc, 4)}
    )

    # Packet loss: 1%, 5%, 10%
    for drop_pct in [1.0, 5.0, 10.0]:
        X_corrupt = apply_packet_loss(Xs, drop_pct, rng)
        p = model.predict_proba(X_corrupt)[:, 1]
        pred = (p >= 0.5).astype(int)
        results.append(
            {
                "scenario": "packet_loss",
                "params": {"drop_pct": drop_pct},
                "f1": round(float(f1_score(y, pred)), 4),
                "roc_auc": round(float(roc_auc_score(y, p)), 4),
            }
        )

    # Sensor noise: 0.1, 0.3, 0.5 std
    for noise_std in [0.1, 0.3, 0.5]:
        X_corrupt = apply_sensor_noise(Xs, noise_std, rng)
        p = model.predict_proba(X_corrupt)[:, 1]
        pred = (p >= 0.5).astype(int)
        results.append(
            {
                "scenario": "sensor_noise",
                "params": {"noise_std": noise_std},
                "f1": round(float(f1_score(y, pred)), 4),
                "roc_auc": round(float(roc_auc_score(y, p)), 4),
            }
        )

    # Outlier injection: 0.5%, 2%, 5%
    for pct in [0.5, 2.0, 5.0]:
        X_corrupt = apply_outlier_injection(Xs, pct, rng)
        p = model.predict_proba(X_corrupt)[:, 1]
        pred = (p >= 0.5).astype(int)
        results.append(
            {
                "scenario": "outlier_injection",
                "params": {"pct": pct},
                "f1": round(float(f1_score(y, pred)), 4),
                "roc_auc": round(float(roc_auc_score(y, p)), 4),
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_f1": round(baseline_f1, 4),
        "baseline_roc_auc": round(baseline_auc, 4),
        "scenarios": results,
        "robustness_targets": {
            "f1_degradation_max_pct": 15,
            "description": "F1 should not drop more than 15% under 5% packet loss or 0.3 std noise",
        },
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "edge-ml-robustness.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"\nSaved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
