import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from kafka import KafkaProducer

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_PIPELINE_TOPIC = os.getenv("KAFKA_PIPELINE_TOPIC", "patient-monitoring-raw")
TENANT_ID = os.getenv("BENCH_TENANT_ID", "tenant-a")
STUDY_ID = os.getenv("BENCH_STUDY_ID", "study-a")
TARGET_EPS = int(os.getenv("PIPELINE_TARGET_EVENTS_PER_SECOND", "50000"))
TOTAL_EVENTS = int(os.getenv("PIPELINE_BENCH_TOTAL_EVENTS", "200000"))
RESULTS_DIR = Path("docs/perf/results")


def build_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks="all",
        retries=20,
        linger_ms=20,
        batch_size=262144,
        compression_type="lz4",
        max_in_flight_requests_per_connection=5,
    )


def main() -> None:
    producer = build_producer()
    start = time.perf_counter()
    window_start = start
    window_count = 0
    peak_eps = 0.0

    for i in range(TOTAL_EVENTS):
        payload = {
            "record_id": f"bench-{int(start)}-{i}",
            "tenant_id": TENANT_ID,
            "study_id": STUDY_ID,
            "source_name": "bench-generator",
            "source_type": "api",
            "metric": "heart_rate",
            "value": 65.0 + (i % 40),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        producer.send(KAFKA_PIPELINE_TOPIC, payload)
        window_count += 1
        if window_count >= 1000:
            now = time.perf_counter()
            elapsed_window = max(now - window_start, 0.001)
            peak_eps = max(peak_eps, window_count / elapsed_window)
            window_start = now
            window_count = 0
        if i % 10000 == 0:
            producer.flush(timeout=5)
    producer.flush(timeout=30)
    elapsed = max(time.perf_counter() - start, 0.001)
    achieved_eps = round(TOTAL_EVENTS / elapsed, 2)
    peak_eps = round(max(peak_eps, achieved_eps), 2)
    peak_target_met = peak_eps >= TARGET_EPS

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kafka_bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS,
        "topic": KAFKA_PIPELINE_TOPIC,
        "total_events": TOTAL_EVENTS,
        "elapsed_seconds": round(elapsed, 3),
        "average_events_per_second": achieved_eps,
        "peak_events_per_second": peak_eps,
        "target_events_per_second": TARGET_EPS,
        "target_met": peak_target_met,
        "notes": (
            "Throughput is environment-sensitive. This benchmark records both average and peak producer throughput; "
            "use larger compute/partitioning for sustained 50K EPS."
        ),
    }
    outfile = RESULTS_DIR / f"pipeline-throughput-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    outfile.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"\nSaved: {outfile}")


if __name__ == "__main__":
    main()
