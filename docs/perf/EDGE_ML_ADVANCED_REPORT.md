# Edge ML Advanced Report

Generated at: `2026-03-14T23:01:24.194750+00:00`

## Model Quality

- Dataset size: **60000**
- Positive class rate: **0.0091**
- Test ROC-AUC: **1.0**
- Test PR-AUC: **0.9998**
- Test F1: **0.986**
- Calibration ECE: **0.000208**

## Runtime Performance

- Throughput: **21208.2 inf/s**
- p50 latency: **0.0412 ms**
- p95 latency: **0.0777 ms**
- p99 latency: **0.1627 ms**
- Runtime target met: **True**

## Production Maturity Controls

- Calibrated classifier for probability reliability.
- Drift baseline exported for feature-distribution monitoring.
- Thresholded classification aligned to safety-oriented edge inference.

## Artifacts

- `docs/perf/results/edge-ml-advanced-metrics.json`
- `docs/perf/results/edge-ml-runtime-20260314-230124.json`
- `apps/ios-edge-module/Resources/tflite/advanced_scaler_drift_baseline.json`
