# iOS Edge Module Report

Generated at: 2026-03-14T22:17:15.280527+00:00

## Executive Summary

- Daily sensor readings validated: **10000**
- Observed reliability: **0.9975**
- Reliability target: **0.997**
- Target met: **True**
- Baseline cloud cost: **$12000.0/month**
- Estimated cloud cost after edge offload: **$9000.0/month**
- Estimated savings: **$3000.0/month**

## Architecture Summary

- SwiftUI application with Core Data persistence for offline-first buffering.
- On-device inference through TensorFlow Lite bridge (`EdgeInferenceEngine`).
- Background upload pattern marks local records as synced.

## Reliability Method

- Reliability benchmark simulates sensor ingestion, local persistence, inference, and upload outcomes.
- Source result file: `docs/perf/results/ios-edge-reliability-20260314-221715.json`.
- Target threshold aligns with 99.7% reliability objective for 10,000+ daily readings.

## Cost Method

- Cloud savings estimate uses baseline cloud spend and edge-offload ratio.
- This should be replaced by billing-export evidence for production reporting.

## Reproduce

```bash
make bench-ios-edge-reliability
make ios-edge-report
```
