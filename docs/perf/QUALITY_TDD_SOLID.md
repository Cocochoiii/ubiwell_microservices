# TDD and SOLID Guide

This guide documents the quality strategy used for this project track.

## TDD Workflow

1. Write failing test first (`pytest` / `Jest` / `XCTest`).
2. Implement smallest change to pass.
3. Refactor while keeping tests green.
4. Enforce coverage gates in CI.

## SOLID Mapping

- **Single Responsibility**: logic extracted to small helper modules (`shared/utils/reliability_math.py`, `apps/web-dashboard/src/lib/dashboard.ts`).
- **Open/Closed**: helper functions and service seams support extension without rewriting core flows.
- **Liskov Substitution**: inference fallback path preserves the same output contract (`InferenceResult`).
- **Interface Segregation**: frontend utility API is minimal and focused on dashboard orchestration concerns.
- **Dependency Inversion**: services consume abstractions/helpers, while integration points (Kafka/TFLite/network) are wrapped.

## Coverage Gates

- Backend coverage gate: `--cov-fail-under=92`
- Frontend coverage thresholds in `apps/web-dashboard/jest.config.cjs`

## KPI Evidence

- Test count and coverage outputs are aggregated in:
  - `docs/perf/results/quality-engineering-metrics.json`
  - `docs/perf/QUALITY_ENGINEERING_REPORT.md`
