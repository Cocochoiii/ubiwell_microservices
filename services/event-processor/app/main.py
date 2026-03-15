import json
import logging
import os
import time

import httpx
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from pymongo import MongoClient

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
KAFKA_EVENTS_TOPIC = os.getenv("KAFKA_EVENTS_TOPIC", "study-events")
KAFKA_DLQ_TOPIC = os.getenv("KAFKA_DLQ_TOPIC", "study-events-dlq")
KAFKA_IMPORTS_TOPIC = os.getenv("KAFKA_IMPORTS_TOPIC", "study-imports")
KAFKA_PIPELINE_TOPIC = os.getenv("KAFKA_PIPELINE_TOPIC", "patient-monitoring-raw")
EVENT_MAX_RETRIES = int(os.getenv("EVENT_MAX_RETRIES", "3"))
EVENT_RETRY_BACKOFF_SECONDS = float(os.getenv("EVENT_RETRY_BACKOFF_SECONDS", "0.5"))
MONGO_HOST = os.getenv("MONGO_HOST", "mongo")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB = os.getenv("MONGO_DB", "ubiwell_study")
PARTICIPANT_SERVICE_URL = os.getenv("PARTICIPANT_SERVICE_URL", "http://participant-service:8001")
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")
logger = logging.getLogger(__name__)


def get_consumer(topic: str, group_id: str) -> KafkaConsumer:
    return KafkaConsumer(
        topic,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        group_id=group_id,
    )


def get_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )


def validate_enriched_event(event: dict) -> dict:
    if "tenant_id" not in event:
        raise ValueError("missing tenant_id")
    if "event_id" not in event:
        raise ValueError("missing event_id")
    if "study_id" not in event:
        raise ValueError("missing study_id")
    if "event_type" not in event:
        raise ValueError("missing event_type")
    if "value" not in event:
        raise ValueError("missing value")
    event["processed_at"] = time.time()
    event["processing_version"] = "0.4.0"
    return event


def detect_anomalies(event: dict) -> list[dict]:
    alerts = []
    event_type = event.get("event_type")
    value = event.get("value")
    tenant_id = event.get("tenant_id")
    study_id = event.get("study_id")
    participant_id = event.get("participant_id")

    if event_type == "heart_rate" and (value > 130 or value < 40):
        alerts.append(
            {
                "tenant_id": tenant_id,
                "study_id": study_id,
                "participant_id": participant_id,
                "severity": "high",
                "rule_id": "hr_out_of_range",
                "message": f"heart_rate anomaly detected: {value}",
                "event_id": event.get("event_id"),
                "created_at": time.time(),
            }
        )
    if event_type == "spo2" and value < 90:
        alerts.append(
            {
                "tenant_id": tenant_id,
                "study_id": study_id,
                "participant_id": participant_id,
                "severity": "critical",
                "rule_id": "spo2_low",
                "message": f"spo2 anomaly detected: {value}",
                "event_id": event.get("event_id"),
                "created_at": time.time(),
            }
        )
    return alerts


def push_alert_webhook(alert: dict) -> None:
    if not ALERT_WEBHOOK_URL:
        return
    try:
        httpx.post(ALERT_WEBHOOK_URL, json=alert, timeout=3.0)
    except httpx.HTTPError as exc:
        logger.warning("Alert webhook failed: %s", exc)


def process_event(db, event: dict) -> None:
    event = validate_enriched_event(event)
    event_id = event["event_id"]
    if not event_id:
        raise ValueError("missing event_id")

    events = db["events"]
    aggregates = db["event_aggregates"]
    dedupe = db["event_dedupe"]

    # Idempotent consumer pattern: first-writer-wins on event_id.
    dedupe_result = dedupe.update_one(
        {"event_id": event_id},
        {"$setOnInsert": {"created_at": time.time()}},
        upsert=True,
    )
    if dedupe_result.upserted_id is None:
        return

    study_id = event.get("study_id", "unknown")
    events.insert_one(event)
    aggregates.update_one(
        {"tenant_id": event["tenant_id"], "study_id": study_id},
        {"$inc": {"event_count": 1}},
        upsert=True,
    )
    for alert in detect_anomalies(event):
        db["alerts"].insert_one(alert)
        push_alert_webhook(alert)


def process_import(db, message: dict) -> None:
    if message.get("type") != "participant_import":
        raise ValueError("unsupported import message")
    tenant_id = message.get("tenant_id")
    participant = message.get("participant", {})
    if not tenant_id or not participant:
        raise ValueError("invalid import payload")

    response = httpx.post(
        f"{PARTICIPANT_SERVICE_URL}/participants",
        json={
            "tenant_id": tenant_id,
            "participant_id": participant.get("participant_id"),
            "study_id": participant.get("study_id"),
            "status": participant.get("status", "active"),
        },
        headers={"x-tenant-id": tenant_id},
        timeout=8.0,
    )
    response.raise_for_status()
    db["import_jobs"].update_one(
        {"tenant_id": tenant_id, "import_id": message.get("import_id")},
        {"$inc": {"processed_rows": 1}, "$set": {"updated_at": time.time()}},
        upsert=True,
    )


def process_monitoring_record(db, record: dict) -> None:
    record_id = record.get("record_id")
    tenant_id = record.get("tenant_id")
    study_id = record.get("study_id")
    if not record_id or not tenant_id or not study_id:
        raise ValueError("invalid monitoring record")

    dedupe = db["pipeline_dedupe"]
    dedupe_result = dedupe.update_one(
        {"record_id": record_id},
        {"$setOnInsert": {"created_at": time.time()}},
        upsert=True,
    )
    if dedupe_result.upserted_id is None:
        return

    metric = record.get("metric", "unknown")
    value = record.get("value", 0.0)
    db["raw_patient_monitoring"].insert_one({**record, "processed_at": time.time()})

    # Keep analytics collections warm for dashboards and alerting.
    event_doc = {
        "tenant_id": tenant_id,
        "study_id": study_id,
        "participant_id": record.get("participant_id", "unknown"),
        "event_id": f"raw:{record_id}",
        "event_type": metric,
        "value": value,
        "source_type": record.get("source_type", "collector"),
        "processed_at": time.time(),
    }
    process_event(db, event_doc)


def main() -> None:
    mongo = MongoClient(host=MONGO_HOST, port=MONGO_PORT)
    db = mongo[MONGO_DB]
    db["event_dedupe"].create_index("event_id", unique=True)
    db["events"].create_index("event_id")
    db["event_aggregates"].create_index([("tenant_id", 1), ("study_id", 1)], unique=True)
    db["alerts"].create_index([("tenant_id", 1), ("study_id", 1), ("created_at", -1)])
    db["pipeline_dedupe"].create_index("record_id", unique=True)
    db["raw_patient_monitoring"].create_index([("tenant_id", 1), ("study_id", 1), ("ingested_at", -1)])
    dlq_producer = get_producer()

    while True:
        try:
            event_consumer = get_consumer(KAFKA_EVENTS_TOPIC, "study-event-processor")
            import_consumer = get_consumer(KAFKA_IMPORTS_TOPIC, "study-import-processor")
            pipeline_consumer = get_consumer(KAFKA_PIPELINE_TOPIC, "monitoring-pipeline-processor")
            while True:
                for message in event_consumer.poll(timeout_ms=500).values():
                    for msg in message:
                        payload = msg.value
                        last_error = None
                        processed = False
                        for attempt in range(1, EVENT_MAX_RETRIES + 1):
                            try:
                                process_event(db, payload)
                                processed = True
                                break
                            except Exception as exc:
                                last_error = str(exc)
                                time.sleep(EVENT_RETRY_BACKOFF_SECONDS * attempt)

                        if not processed:
                            dlq_payload = {
                                "event": payload,
                                "error": last_error or "unknown_error",
                                "failed_at": time.time(),
                                "max_retries": EVENT_MAX_RETRIES,
                            }
                            dlq_producer.send(KAFKA_DLQ_TOPIC, dlq_payload)
                            dlq_producer.flush(timeout=1)
                        event_consumer.commit()

                for message in import_consumer.poll(timeout_ms=500).values():
                    for msg in message:
                        payload = msg.value
                        last_error = None
                        processed = False
                        for attempt in range(1, EVENT_MAX_RETRIES + 1):
                            try:
                                process_import(db, payload)
                                processed = True
                                break
                            except Exception as exc:
                                last_error = str(exc)
                                time.sleep(EVENT_RETRY_BACKOFF_SECONDS * attempt)

                        if not processed:
                            dlq_payload = {
                                "event": payload,
                                "error": last_error or "import_unknown_error",
                                "failed_at": time.time(),
                                "max_retries": EVENT_MAX_RETRIES,
                            }
                            dlq_producer.send(KAFKA_DLQ_TOPIC, dlq_payload)
                            dlq_producer.flush(timeout=1)
                        import_consumer.commit()

                for message in pipeline_consumer.poll(timeout_ms=500).values():
                    for msg in message:
                        payload = msg.value
                        last_error = None
                        processed = False
                        for attempt in range(1, EVENT_MAX_RETRIES + 1):
                            try:
                                process_monitoring_record(db, payload)
                                processed = True
                                break
                            except Exception as exc:
                                last_error = str(exc)
                                time.sleep(EVENT_RETRY_BACKOFF_SECONDS * attempt)
                        if not processed:
                            dlq_payload = {
                                "event": payload,
                                "error": last_error or "pipeline_unknown_error",
                                "failed_at": time.time(),
                                "max_retries": EVENT_MAX_RETRIES,
                                "topic": KAFKA_PIPELINE_TOPIC,
                            }
                            dlq_producer.send(KAFKA_DLQ_TOPIC, dlq_payload)
                            dlq_producer.flush(timeout=1)
                        pipeline_consumer.commit()
        except (KafkaError, OSError, RuntimeError, ValueError) as exc:
            logger.warning("Event processor loop restarting after error: %s", exc)
            time.sleep(3)


if __name__ == "__main__":
    main()
