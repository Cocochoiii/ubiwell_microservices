# Model Card: Ubiwell Edge Risk Classifier

## Model Details

- **Model type:** Calibrated Random Forest (sigmoid calibration)
- **Task:** Binary classification (clinical risk flag for wearable telemetry)
- **Input:** 9 features (heart_rate, spo2, resp_rate, temperature_c, motion_index, hr_delta, spo2_delta, hr_var_30s, rr_var_30s)
- **Output:** Risk probability [0, 1]; threshold 0.5 for binary decision

## Intended Use

- **Primary:** On-device screening of wearable telemetry to flag elevated risk for downstream clinical review.
- **Not intended:** Direct clinical diagnosis, replacement of clinician judgment, or use without human-in-the-loop for high-stakes decisions.

## Limitations

- **Data:** Trained on synthetic data; real-world performance may differ. Temporal and demographic distribution shifts are expected.
- **Sensors:** Assumes standard wearable accuracy (e.g., PPG-based HR/SpO2). Uncalibrated or low-quality sensors may degrade performance.
- **Edge constraints:** Model runs on-device; input preprocessing (scaling, imputation) must match training pipeline exactly.
- **Calibration:** Calibration holds for the training distribution; may degrade under significant drift.

## Risk Controls

- **Drift monitoring:** Feature distribution monitored against baseline; alarms at z-score > 3, std ratio > 2, PSI > 0.25.
- **Rollback criteria:** Revert to previous model when F1 < 0.75, ECE > 0.12, or ROC-AUC < 0.82.
- **Human oversight:** All high-risk flags require clinician review before action.
- **Audit trail:** Inference logs retained for debugging and compliance.

## Ethical Considerations

- **Bias:** Synthetic data may not reflect real demographic or clinical diversity; monitor for disparate impact in production.
- **Privacy:** On-device inference minimizes data transmission; no raw telemetry leaves the device for inference.
- **Transparency:** Model card and drift/rollback policies are documented for stakeholders and regulators.

## Evaluation

- **Temporal holdout:** Train weeks 1–3, test week 4 (time-based split).
- **Robustness:** Packet loss, sensor noise, and outlier injection tests; F1 degradation target < 15% under 5% packet loss.
- **Calibration:** ECE reported; target < 0.1.

## References

- Drift baseline: `apps/ios-edge-module/Resources/tflite/advanced_scaler_drift_baseline.json`
- Metrics: `docs/perf/results/edge-ml-advanced-metrics.json`
- Robustness: `docs/perf/results/edge-ml-robustness.json`
