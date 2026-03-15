# Bullet Track Playbook

This monorepo supports five interview-ready tracks. Each track has dedicated commands and evidence outputs so you can demo them independently.

## Track 1: Clinical Workflow Platform (Distributed Microservices)

Goal:

- Multi-tenant FastAPI microservices with PostgreSQL/MongoDB, REST + gRPC, SLO-backed performance.

Run:

```bash
make demo-up
make bench-report
make slo-report
make release-gate
```

Show:

- `docs/perf/SLO_REPORT.md`
- `docs/perf/RELEASE_READINESS_REPORT.md`

## Track 2: Fault-Tolerant Telemetry Pipeline (Kafka)

Goal:

- API/web collectors + event-driven Kafka pipeline with retry/DLQ/idempotency and data-loss reduction evidence.

Run:

```bash
make bench-pipeline-throughput
make bench-data-loss
```

Show:

- `docs/perf/results/pipeline-throughput-*.json`
- `docs/perf/results/data-loss-reduction-*.json`
- `docs/perf/PIPELINE_PRODUCTION_REPORT.md`

## Track 3: Report Optimization + 100+ Dashboard Architecture

Goal:

- Multi-tier cache report engine and metadata-driven role-based dashboards with realtime updates.

Run:

```bash
make bench-report
make load-dashboard
make interview-report
```

Show:

- `docs/perf/INTERVIEW_DEMO_REPORT.md`
- `docs/perf/results/benchmark-*.json`
- `docs/perf/results/k6-dashboard-summary.json`

## Track 4: iOS Edge ML Module (Advanced)

Goal:

- SwiftUI/Core Data edge module with advanced ML pipeline, calibration, drift checks, and latency/performance evidence.

Run:

```bash
make ios-edge-ml-advanced
make bench-edge-ml
make edge-ml-report
make bench-ios-edge-reliability
make ios-edge-report
```

Show:

- `docs/perf/EDGE_ML_ADVANCED_REPORT.md`
- `docs/perf/results/edge-ml-advanced-metrics.json`
- `docs/perf/results/edge-ml-runtime-*.json`
- `docs/perf/IOS_EDGE_REPORT.md`

## Track 5: Engineering Excellence (TDD + Reviews + SOLID)

Goal:

- Pytest/Jest/XCTest quality gates with KPI evidence for coverage, defect reduction, and time savings.

Run:

```bash
make quality-evidence
make quality-report
```

Show:

- `docs/perf/QUALITY_ENGINEERING_REPORT.md`
- `docs/perf/results/quality-engineering-metrics.json`

## One-Command Full Demonstration

```bash
make board-ready
```

Primary summary:

- `docs/perf/BOARD_READINESS_SUMMARY.md`
