# UbiWell Interview Demo Report

Generated at: `2026-03-14T21:58:47.801273+00:00`

## Executive Summary

- Built and validated a production-style reporting platform with role-aware realtime dashboards.
- Demonstrated report optimization via multi-tier caching and algorithmic redesign.
- Collected reproducible operational evidence (benchmarks, load tests, observability screenshots, SLO report).

## Performance Summary

- Benchmark rounds: `5`
- Naive average: `0.294282s`
- Optimized average: `0.002455s`
- Improvement: `99.17%`
- 85% target met: `True`

## Technical Highlights

- L1 in-memory cache in `report-service`
- L2 Redis cache with invalidation endpoint
- L3 precomputed Mongo aggregates
- role-based dashboard metadata templates (120 generated)
- websocket realtime stream with tenant-aware auth

## Evidence Artifacts

- API docs: `docs/perf/screenshots/api-docs.png`
- Web dashboard: `docs/perf/screenshots/web-dashboard.png`
- Grafana overview: `docs/perf/screenshots/grafana-overview.png`
- Prometheus: `docs/perf/screenshots/prometheus.png`
- Jaeger: `docs/perf/screenshots/jaeger.png`

## Reproduce This Report

```bash
make demo-up
make test-backend
make bench-report
make load-dashboard
make e2e-flow
make capture-screenshots
make interview-report
```

## Resume Mapping

This demo supports claims around:
- report optimization using caching + algorithm design
- high-scale dashboard delivery with role-based access controls
- realtime operational visibility with production observability
