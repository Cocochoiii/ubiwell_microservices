#!/usr/bin/env python3
"""Advanced edge-ML training/evaluation for interview-grade evidence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "docs" / "perf" / "results"
ARTIFACTS_DIR = ROOT / "apps" / "ios-edge-module" / "Resources" / "tflite"


def synthetic_dataset(n: int = 60000, seed: int = 11) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    hr = rng.normal(82, 16, n)
    spo2 = rng.normal(96, 2.2, n)
    rr = rng.normal(15, 4, n)
    temp = rng.normal(36.8, 0.8, n)
    motion = rng.gamma(2.0, 0.2, n)

    # Time-window features approximating edge telemetry windows.
    hr_delta = rng.normal(0, 6, n)
    spo2_delta = rng.normal(0, 1.2, n)
    hr_var_30s = np.abs(rng.normal(3.0, 1.5, n))
    rr_var_30s = np.abs(rng.normal(1.2, 0.8, n))

    X = np.vstack([hr, spo2, rr, temp, motion, hr_delta, spo2_delta, hr_var_30s, rr_var_30s]).T
    risk = (
        (hr > 125)
        | (spo2 < 90)
        | (rr > 28)
        | (temp > 39.2)
        | ((hr_var_30s > 8) & (spo2_delta < -2.5))
        | ((motion > 1.6) & (hr > 115))
    )
    y = risk.astype(int)
    return X.astype(np.float32), y


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, bins: int = 15) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (y_prob >= lo) & (y_prob < hi if i < bins - 1 else y_prob <= hi)
        if not np.any(mask):
            continue
        confidence = float(np.mean(y_prob[mask]))
        accuracy = float(np.mean(y_true[mask]))
        ece += abs(confidence - accuracy) * (np.sum(mask) / len(y_prob))
    return float(ece)


def evaluate_cv(X: np.ndarray, y: np.ndarray) -> dict[str, float]:
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=11)
    aucs, prs, f1s = [], [], []
    for train_idx, test_idx in skf.split(X, y):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        base = RandomForestClassifier(n_estimators=160, max_depth=10, random_state=11, n_jobs=-1)
        model = CalibratedClassifierCV(base, method="sigmoid", cv=3)
        model.fit(X_train_scaled, y_train)
        p = model.predict_proba(X_test_scaled)[:, 1]
        pred = (p >= 0.5).astype(int)
        aucs.append(roc_auc_score(y_test, p))
        prs.append(average_precision_score(y_test, p))
        f1s.append(f1_score(y_test, pred))
    return {
        "cv_roc_auc": round(float(np.mean(aucs)), 4),
        "cv_pr_auc": round(float(np.mean(prs)), 4),
        "cv_f1": round(float(np.mean(f1s)), 4),
    }


def main() -> int:
    X, y = synthetic_dataset()
    cv_metrics = evaluate_cv(X, y)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=11, stratify=y)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    base = RandomForestClassifier(n_estimators=220, max_depth=12, random_state=11, n_jobs=-1)
    model = CalibratedClassifierCV(base, method="sigmoid", cv=3)
    model.fit(X_train_scaled, y_train)

    probs = model.predict_proba(X_test_scaled)[:, 1]
    preds = (probs >= 0.5).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(y_test, preds, average="binary", zero_division=0)
    roc_auc = roc_auc_score(y_test, probs)
    pr_auc = average_precision_score(y_test, probs)
    brier = brier_score_loss(y_test, probs)
    ece = expected_calibration_error(y_test, probs)

    # Drift baseline for production monitoring (population feature means/std).
    drift_baseline = {
        "feature_mean": scaler.mean_.tolist(),
        "feature_scale": scaler.scale_.tolist(),
        "feature_names": [
            "heart_rate",
            "spo2",
            "resp_rate",
            "temperature_c",
            "motion_index",
            "hr_delta",
            "spo2_delta",
            "hr_var_30s",
            "rr_var_30s",
        ],
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": int(len(X)),
        "positive_rate": round(float(np.mean(y)), 4),
        "test_roc_auc": round(float(roc_auc), 4),
        "test_pr_auc": round(float(pr_auc), 4),
        "test_precision": round(float(precision), 4),
        "test_recall": round(float(recall), 4),
        "test_f1": round(float(f1), 4),
        "test_brier": round(float(brier), 6),
        "test_ece": round(float(ece), 6),
        "cv": cv_metrics,
        "threshold": 0.5,
    }
    (RESULTS_DIR / "edge-ml-advanced-metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (ARTIFACTS_DIR / "advanced_scaler_drift_baseline.json").write_text(json.dumps(drift_baseline, indent=2), encoding="utf-8")
    print("Saved advanced metrics and drift baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
