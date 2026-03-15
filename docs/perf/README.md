# Performance Methodology

This folder documents the optimization track for report generation and dashboard rendering.

## Goal

- Improve report generation time by 85% (target from 8h to 1.2h equivalent batch runtime).
- Support 1,000+ daily users with role-based, realtime dashboards.

## Optimization Strategy

1. L1 in-memory cache in `report-service`.
2. L2 Redis cache with TTL and explicit invalidation endpoint.
3. L3 precomputed aggregates in Mongo (`report_aggregates`) with refresh window.
4. Optimized grouping algorithm replaces repeated scans/N+1 loops.
5. Role-based template rendering in frontend for 100+ dashboards without hardcoding.

## Benchmark Procedure

1. Seed realistic data with `make seed-demo`.
2. Run benchmark script:

```bash
python3 benchmarks/report_benchmark.py
```

3. Compare `naive_avg_seconds` vs `optimized_avg_seconds`.
4. Save generated JSON in `docs/perf/results/` and capture Grafana/Jaeger screenshots.

## Evidence Checklist

- Benchmark JSON output (`docs/perf/results/*.json`)
- Grafana latency dashboard screenshot
- Prometheus SLO alert status screenshot
- Jaeger trace showing report-service call path
- Web dashboard screenshot showing role-based + realtime widgets
