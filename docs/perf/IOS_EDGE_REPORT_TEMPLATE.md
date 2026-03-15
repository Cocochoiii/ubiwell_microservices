# iOS Edge Module Report

Generated at: {generated_at}

## Executive Summary

- Daily sensor readings validated: **{readings}**
- Observed reliability: **{reliability}**
- Reliability target: **{reliability_target}**
- Target met: **{target_met}**
- Baseline cloud cost: **${baseline_cost}/month**
- Estimated cloud cost after edge offload: **${cost_after}/month**
- Estimated savings: **${monthly_savings}/month**

## Architecture Summary

- SwiftUI application with Core Data persistence for offline-first buffering.
- On-device inference through TensorFlow Lite bridge (`EdgeInferenceEngine`).
- Background upload pattern marks local records as synced.

## Reliability Method

- Reliability benchmark simulates sensor ingestion, local persistence, inference, and upload outcomes.
- Source result file: `{source_file}`.
- Target threshold aligns with 99.7% reliability objective for 10,000+ daily readings.

## Cost Method

- Cloud savings estimate uses baseline cloud spend and edge-offload ratio.
- This should be replaced by billing-export evidence for production reporting.

## Reproduce

```bash
make bench-ios-edge-reliability
make ios-edge-report
```
