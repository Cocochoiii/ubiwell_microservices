# Pipeline Production Validation

This report captures evidence for the pipeline bullet:

- Fault-tolerant scalable pipelines for patient-monitoring ingestion
- API + BeautifulSoup/Selenium collectors
- Kafka event-driven architecture with 50K events/s peak target
- Data loss reduction target: 15%

## Architecture

- Collectors: `services/collector-service`
  - API collection endpoint: `/pipeline/collect/api`
  - Web collection endpoint: `/pipeline/collect/web`
  - 500-hour simulation endpoint: `/pipeline/collect/simulate-500h`
- Broker: Redpanda (`KAFKA_PIPELINE_TOPIC=patient-monitoring-raw`)
- Processor: `services/event-processor` (`monitoring-pipeline-processor` group)
  - Manual offset commit (`enable_auto_commit=False`)
  - Retry/backoff + DLQ on failure
  - Idempotent dedupe (`pipeline_dedupe` index)
  - Writes to `raw_patient_monitoring` and analytics event collections

## Reliability Controls

- Producer durability: `acks=all`, retries, batching, compression (`lz4`)
- Consumer durability: manual commit after success or DLQ handoff
- Recovery: existing DLQ replay tooling (`make replay-dlq`)
- Checkpointing: collector job outputs persisted in `pipeline_checkpoints`

## Benchmark Commands

```bash
make bench-pipeline-throughput
make bench-data-loss
```

## Evidence Files

- `docs/perf/results/pipeline-throughput-*.json`
- `docs/perf/results/data-loss-reduction-*.json`

## Notes

- Throughput strongly depends on host resources and partitioning.
- For production 50K EPS validation, run with increased Redpanda resources and tuned partition/consumer parallelism.
