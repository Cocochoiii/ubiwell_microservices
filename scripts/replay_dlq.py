#!/usr/bin/env python3
"""
Replay failed events from DLQ topic back to main events topic.

This script is intentionally simple and local-dev friendly:
- Reads messages from KAFKA_DLQ_TOPIC
- Extracts original `event`
- Re-publishes to KAFKA_EVENTS_TOPIC
"""

import json
import os
import sys
import time
from typing import Any

from kafka import KafkaConsumer, KafkaProducer

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_EVENTS_TOPIC = os.getenv("KAFKA_EVENTS_TOPIC", "study-events")
KAFKA_DLQ_TOPIC = os.getenv("KAFKA_DLQ_TOPIC", "study-events-dlq")
REPLAY_LIMIT = int(os.getenv("DLQ_REPLAY_LIMIT", "100"))
GROUP_ID = os.getenv("DLQ_REPLAY_GROUP_ID", f"dlq-replayer-{int(time.time())}")


def make_consumer() -> KafkaConsumer:
    return KafkaConsumer(
        KAFKA_DLQ_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        group_id=GROUP_ID,
        consumer_timeout_ms=2000,
    )


def make_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )


def extract_event(dlq_payload: dict[str, Any]) -> dict[str, Any] | None:
    event = dlq_payload.get("event")
    if isinstance(event, dict):
        return event
    return None


def main() -> int:
    consumer = make_consumer()
    producer = make_producer()

    replayed = 0
    skipped = 0

    try:
        for message in consumer:
            dlq_payload = message.value
            event = extract_event(dlq_payload)
            if event is None:
                skipped += 1
                continue

            producer.send(KAFKA_EVENTS_TOPIC, event)
            replayed += 1

            if replayed >= REPLAY_LIMIT:
                break

        producer.flush(timeout=5)
        consumer.commit()
    except Exception as exc:
        print(f"DLQ replay failed: {exc}", file=sys.stderr)
        return 1
    finally:
        consumer.close()
        producer.close()

    print(
        f"DLQ replay complete. replayed={replayed} skipped={skipped} "
        f"source_topic={KAFKA_DLQ_TOPIC} target_topic={KAFKA_EVENTS_TOPIC}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
