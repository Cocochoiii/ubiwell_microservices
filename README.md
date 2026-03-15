# UbiWell Study Workflow Platform

Production-style distributed platform for study workflows, telemetry ingestion, optimized reporting, and role-based realtime dashboards.

## Core Capabilities

- Python microservices (`FastAPI`) with tenant-aware auth and RBAC
- `PostgreSQL` + `MongoDB` + `Redis`
- External REST APIs + internal `gRPC` contracts
- Kafka-compatible async pipeline (`Redpanda`)
- iOS edge module (`SwiftUI` + Core Data + TensorFlow Lite bridge)
- Observability stack: Prometheus, Grafana, OpenTelemetry, Jaeger
- Reliability patterns: retries, DLQ, idempotency, circuit breaker, cache invalidation
- Evidence tooling: benchmarks, load tests, screenshots, interview-ready reports
- TDD and review track with pytest/Jest/XCTest quality gates

## Service Map

- `api-gateway`: auth, RBAC, rate limits, routing, audit logs
- `participant-service`: participant CRUD + gRPC
- `survey-service`: survey responses + gRPC
- `ingestion-service`: telemetry validation/enrichment + queue publish
- `collector-service`: API + BeautifulSoup/Selenium data collectors with Kafka publish checkpoints
- `event-processor`: queue consumers, retry/backoff, DLQ, anomaly rules
- `analytics-service`: cohort summaries and alert/report endpoints
- `report-service`: multi-tier cached report generation + benchmark endpoint
- `realtime-service`: websocket updates with role-aware payload filtering
- `apps/web-dashboard`: React/TypeScript frontend with metadata-driven dashboards
- `apps/ios-edge-module`: SwiftUI edge app scaffold with Core Data and on-device inference bridge

## Quick Start

1. Prepare environment:

```bash
cp .env.example .env
```

2. Start stack and seed demo data:

```bash
make demo-up
```

Optional (enable Selenium-backed collectors):

```bash
docker compose --profile collector up -d selenium collector-service
```

3. Open:

- API Gateway: `http://localhost:8000/docs`
- Web Dashboard: `http://localhost:5173`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (`admin`/`admin`)
- Jaeger: `http://localhost:16686`

## Authentication

Get a token:

```bash
curl -X POST http://localhost:8000/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"researcher","password":"researcher123"}'
```

Use token + tenant header:

```bash
curl http://localhost:8000/participants \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: tenant-a"
```

Security notes:

- Password verification uses bcrypt hashing.
- For non-demo mode use `APP_ENV=prod` and short token TTL via `TOKEN_EXPIRES_MINUTES_PROD`.
- Generate hashed `AUTH_USERS_JSON` using `python3 scripts/hash_demo_users.py`.

## Key API Examples

Cached report endpoint:

```bash
curl "http://localhost:8000/reports/studies/study-a?page=1&page_size=20&participant_filter=p-10" \
  -H 'Authorization: Bearer <TOKEN>' \
  -H 'x-tenant-id: tenant-a'
```

Report benchmark endpoint:

```bash
curl "http://localhost:8000/reports/studies/study-a/benchmark?rounds=5" \
  -H 'Authorization: Bearer <TOKEN>' \
  -H 'x-tenant-id: tenant-a'
```

Fault-tolerant pipeline collection (API/web + Kafka):

```bash
curl -X POST http://localhost:8000/pipeline/collect/api \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: tenant-a" \
  -H "Content-Type: application/json" \
  -d '{"study_id":"study-a","source_name":"wearable-rest","endpoint":"https://example.com","hours":24,"points_per_minute":2}'
```

500-hour simulation job:

```bash
curl -X POST http://localhost:8000/pipeline/collect/simulate-500h \
  -H "Authorization: Bearer <TOKEN>" \
  -H "x-tenant-id: tenant-a"
```

## iOS Edge Track (New)

This repo now includes `apps/ios-edge-module` for the iOS bullet:

- SwiftUI app shell and pipeline service
- Core Data schema (`SensorReading`) for offline-first persistence
- TensorFlow Lite inference bridge (`EdgeInferenceEngine`)
- Reliability and cost evidence scripts

Build model + reliability evidence:

```bash
make ios-edge-ml
make bench-ios-edge-reliability
make ios-edge-report
```

Build advanced ML + runtime evidence:

```bash
make ios-edge-ml-advanced
make bench-edge-ml
make edge-ml-report
```

Bullet-by-bullet demo playbook:

- `docs/perf/BULLET_TRACKS.md`

## Quality Engineering Track (TDD + SOLID)

This repo now includes an explicit quality track for the final bullet:

- `pytest` backend tests with coverage gate (92% target on quality modules)
- `Jest` frontend tests with coverage thresholds
- `XCTest` scaffold for iOS edge module
- KPI report generation for test count, bug reduction, and weekly time savings

Run quality evidence pipeline:

```bash
make quality-evidence
```

Generate report only:

```bash
make quality-report
```

## Industry Release Gate

For production-style governance, this repo includes a release gate that validates all major bullet evidence in one place:

- report optimization target (`>=85%`)
- dashboard/API SLO checks from k6
- quality engineering KPIs (coverage/tests/bug reduction/hours saved)
- iOS edge reliability/cost outcomes
- optional strict pipeline gate (throughput + data loss reduction artifacts)

Run the gate:

```bash
make release-gate
```

Run strict mode (requires pipeline artifacts too):

```bash
make release-gate-strict
```

One-command executive run (full strict pipeline + summary):

```bash
make board-ready
```

## Security and Compliance Hardening

This repo now includes enterprise-style hardening controls:

- Dependency vulnerability scanning (`pip-audit` + `npm audit` wrappers)
- Secret scanning (regex + entropy heuristics)
- Container hardening scan (Dockerfile policy checks + optional Trivy image scan)
- SBOM generation (CycloneDX-like JSON)
- Signed release checklist with verification workflow

Run all controls:

```bash
make security-compliance
```

Checklist signing/verify:

```bash
make security-sign-checklist
make security-verify-checklist
```

## Industry-Level Validation Flow

Run this sequence for interview evidence:

```bash
make test-backend
make bench-report
make bench-pipeline-throughput
make bench-data-loss
make bench-ios-edge-reliability
make ios-edge-report
make quality-evidence
make security-compliance
make release-gate
make load-dashboard
make e2e-flow
make capture-screenshots
make interview-report
make slo-report
```

Or use the bundled pipeline:

```bash
make interview-demo
```

## Evidence Outputs

- Benchmarks: `docs/perf/results/benchmark-*.json`
- Pipeline throughput benchmark: `docs/perf/results/pipeline-throughput-*.json`
- Data loss reduction evidence: `docs/perf/results/data-loss-reduction-*.json`
- iOS edge reliability evidence: `docs/perf/results/ios-edge-reliability-*.json`
- iOS edge report: `docs/perf/IOS_EDGE_REPORT.md`
- Edge ML advanced report: `docs/perf/EDGE_ML_ADVANCED_REPORT.md`
- Quality metrics JSON: `docs/perf/results/quality-engineering-metrics.json`
- Quality report: `docs/perf/QUALITY_ENGINEERING_REPORT.md`
- Release gate JSON: `docs/perf/results/release-gate-report.json`
- Release gate report: `docs/perf/RELEASE_READINESS_REPORT.md`
- Board summary: `docs/perf/BOARD_READINESS_SUMMARY.md`
- Dependency vuln report: `docs/perf/DEPENDENCY_VULN_REPORT.md`
- Secret scan report: `docs/perf/SECRET_SCAN_REPORT.md`
- Container scan report: `docs/perf/CONTAINER_SCAN_REPORT.md`
- SBOM report: `docs/perf/SBOM_REPORT.md`
- Signed release checklist: `docs/perf/SIGNED_RELEASE_CHECKLIST.md`
- k6 load summary: `docs/perf/results/k6-dashboard-summary.json`
- Screenshots: `docs/perf/screenshots/`
- Interview narrative: `docs/perf/INTERVIEW_DEMO_REPORT.md`
- SLO/error budget status: `docs/perf/SLO_REPORT.md`

## Reliability and Performance Features

- Multi-tier reporting cache (L1 in-memory, L2 Redis, L3 precomputed aggregates)
- Cache invalidation API for consistency during updates
- Event retries with backoff + DLQ replay tooling
- Idempotent ingestion and consumer-side deduplication
- Collector pipeline with checkpointed jobs and manual Kafka offset commits
- API and web scraping collectors (`httpx` + BeautifulSoup + Selenium) publishing to Kafka
- Realtime role-scoped websocket payloads
- Frontend lazy loading for heavy chart bundle
- Bundle budget check enforced in CI

## CI Coverage

Workflow at `.github/workflows/ci.yml` includes:

- Python dependency install + compile checks for all services
- Backend automated tests (`pytest`)
- Frontend build + bundle budget enforcement
- Docker Compose validation

## Useful Commands

- `make up` / `make down` / `make logs`
- `make seed-demo`
- `make replay-dlq`
- `make collect-500h`
- `make bench-pipeline-throughput`
- `make bench-data-loss`
- `make ios-edge-ml`
- `make ios-edge-ml-advanced`
- `make bench-ios-edge-reliability`
- `make bench-edge-ml`
- `make edge-ml-report`
- `make ios-edge-report`
- `make test-backend-coverage`
- `make test-frontend-jest`
- `make quality-report`
- `make quality-evidence`
- `make security-deps`
- `make security-secrets`
- `make security-containers`
- `make security-sbom`
- `make security-sign-checklist`
- `make security-verify-checklist`
- `make security-compliance`
- `make release-gate`
- `make release-gate-strict`
- `make industry-readiness`
- `make board-ready`
- `make chaos-test`
- `make proto-gen`
- `make k8s-apply`

## Kubernetes

Starter manifests are under `k8s/` and include:

- app Deployments/Services
- Postgres, MongoDB, Redis, Redpanda
- ConfigMap and Secret wiring
