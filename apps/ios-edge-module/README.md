# iOS Edge Module

This module scaffolds an interview-ready iOS edge architecture for:

- SwiftUI app shell
- Core Data local persistence
- TensorFlow Lite inference bridge
- Offline-first sensor buffering with background upload hooks

## Folder Layout

- `UbiWellEdge/App`: app entry and shell UI
- `UbiWellEdge/Data`: Core Data stack and entity classes
- `UbiWellEdge/ML`: TFLite bridge and inference result mapping
- `UbiWellEdge/Services`: sensor processing pipeline and reliability tracking
- `UbiWellEdge/UbiWellEdge.xcdatamodeld`: Core Data schema
- `Resources/tflite`: exported TFLite models and preprocessing metadata

## Xcode Setup

1. Create a new iOS App project in Xcode named `UbiWellEdge`.
2. Copy this folder's `UbiWellEdge/` source files into the project target.
3. Add `TensorFlowLiteSwift` with Swift Package Manager:
   - URL: `https://github.com/tensorflow/tensorflow`
   - Product: `TensorFlowLiteSwift`
4. Add model assets:
   - `Resources/tflite/sensor_classifier.tflite`
   - `Resources/tflite/scaler.json`
5. Set deployment target to iOS 16+ and run.

## Data Flow

1. Sensor values are ingested from HealthKit/device SDK adapters.
2. Raw data is persisted in Core Data (`SensorReading`).
3. Local model infers class/score on-device using TFLite.
4. Tagged records are queued for upstream sync.
5. Upload acknowledgements mark records as `isUploaded=true`.

## Evidence

Use repo commands:

- `make bench-ios-edge-reliability`
- `make ios-edge-report`

Artifacts land in `docs/perf/results/` and `docs/perf/IOS_EDGE_REPORT.md`.
