import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from kafka import KafkaAdminClient, KafkaProducer
from kafka.errors import KafkaError
from kafka.admin import NewTopic
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

app = FastAPI(title="Ingestion Service", version="0.4.0")
Instrumentator().instrument(app).expose(app)
logger = logging.getLogger(__name__)

# In production this is a queue/broker sink (Kafka/RabbitMQ).
INGESTION_BUFFER: list[dict[str, Any]] = []
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
KAFKA_EVENTS_TOPIC = os.getenv("KAFKA_EVENTS_TOPIC", "study-events")
KAFKA_DLQ_TOPIC = os.getenv("KAFKA_DLQ_TOPIC", "study-events-dlq")
KAFKA_IMPORTS_TOPIC = os.getenv("KAFKA_IMPORTS_TOPIC", "study-imports")
KAFKA_PIPELINE_TOPIC = os.getenv("KAFKA_PIPELINE_TOPIC", "patient-monitoring-raw")
KAFKA_PIPELINE_DLQ_TOPIC = os.getenv("KAFKA_PIPELINE_DLQ_TOPIC", "patient-monitoring-dlq")
KAFKA_PIPELINE_PARTITIONS = int(os.getenv("KAFKA_PIPELINE_PARTITIONS", "8"))
IDEMPOTENCY_WINDOW_SECONDS = int(os.getenv("IDEMPOTENCY_WINDOW_SECONDS", "600"))
INGESTION_BUFFER_MAX_SIZE = int(os.getenv("INGESTION_BUFFER_MAX_SIZE", "10000"))
BUFFER_RETRY_INTERVAL_SECONDS = float(os.getenv("BUFFER_RETRY_INTERVAL_SECONDS", "2.0"))

PRODUCER = None
SEEN_EVENT_IDS: dict[str, float] = {}
SEEN_EVENT_IDS_LOCK = threading.Lock()
BUFFER_LOCK = threading.Lock()
BUFFERED_EVENT_IDS: set[str] = set()


def setup_tracing() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "ingestion-service"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


setup_tracing()


def get_producer() -> KafkaProducer | None:
    global PRODUCER
    if PRODUCER is not None:
        return PRODUCER

    try:
        PRODUCER = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
            retries=20,
            linger_ms=20,
            batch_size=262144,
            compression_type="lz4",
            max_in_flight_requests_per_connection=5,
        )
    except KafkaError as exc:
        logger.warning("Kafka producer initialization failed: %s", exc)
        PRODUCER = None
    return PRODUCER


def ensure_topics() -> None:
    try:
        admin = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
        existing_topics = set(admin.list_topics())
        to_create = []
        topic_partitions = {
            KAFKA_EVENTS_TOPIC: 1,
            KAFKA_DLQ_TOPIC: 1,
            KAFKA_IMPORTS_TOPIC: 1,
            KAFKA_PIPELINE_TOPIC: KAFKA_PIPELINE_PARTITIONS,
            KAFKA_PIPELINE_DLQ_TOPIC: 1,
        }
        for topic, partitions in topic_partitions.items():
            if topic not in existing_topics:
                to_create.append(NewTopic(name=topic, num_partitions=partitions, replication_factor=1))
        if to_create:
            admin.create_topics(new_topics=to_create, validate_only=False)
        admin.close()
    except Exception as exc:
        # Topic bootstrap is best-effort in local dev, but failures should be visible.
        logger.warning("Topic bootstrap failed: %s", exc)


def prune_idempotency_keys(now_epoch: float) -> None:
    stale_ids = [key for key, ts in SEEN_EVENT_IDS.items() if now_epoch - ts > IDEMPOTENCY_WINDOW_SECONDS]
    for key in stale_ids:
        SEEN_EVENT_IDS.pop(key, None)


def publish_event(event: dict[str, Any]) -> None:
    producer = get_producer()
    if producer is None:
        raise RuntimeError("kafka producer unavailable")
    producer.send(KAFKA_EVENTS_TOPIC, event)
    producer.flush(timeout=1)


def buffer_event(event: dict[str, Any], event_id: str) -> bool:
    with BUFFER_LOCK:
        if event_id in BUFFERED_EVENT_IDS:
            return True
        if len(INGESTION_BUFFER) >= INGESTION_BUFFER_MAX_SIZE:
            raise RuntimeError("local ingestion buffer is full")
        INGESTION_BUFFER.append(event)
        BUFFERED_EVENT_IDS.add(event_id)
    return False


def flush_buffer_once() -> int:
    flushed = 0
    while True:
        with BUFFER_LOCK:
            if not INGESTION_BUFFER:
                break
            event = INGESTION_BUFFER[0]
        event_id = str(event.get("event_id", ""))

        # If this id was successfully published via a retrying client request, discard stale buffered copy.
        if event_id:
            with SEEN_EVENT_IDS_LOCK:
                prune_idempotency_keys(datetime.now(timezone.utc).timestamp())
                if event_id in SEEN_EVENT_IDS:
                    with BUFFER_LOCK:
                        INGESTION_BUFFER.pop(0)
                        BUFFERED_EVENT_IDS.discard(event_id)
                    continue

        try:
            publish_event(event)
        except (KafkaError, RuntimeError, OSError, TimeoutError) as exc:
            logger.warning("Buffered event flush paused due to publish failure: %s", exc)
            break

        with BUFFER_LOCK:
            INGESTION_BUFFER.pop(0)
            BUFFERED_EVENT_IDS.discard(event_id)
        if event_id:
            with SEEN_EVENT_IDS_LOCK:
                SEEN_EVENT_IDS[event_id] = datetime.now(timezone.utc).timestamp()
        flushed += 1
    return flushed


def buffer_retry_loop() -> None:
    while True:
        time.sleep(BUFFER_RETRY_INTERVAL_SECONDS)
        try:
            flushed = flush_buffer_once()
            if flushed:
                logger.info("Flushed %s buffered ingestion events to Kafka", flushed)
        except Exception as exc:
            logger.warning("Buffer flush loop failed: %s", exc)


@app.on_event("startup")
def startup() -> None:
    ensure_topics()
    threading.Thread(target=buffer_retry_loop, daemon=True).start()


class EventIngest(BaseModel):
    tenant_id: str | None = None
    event_id: str = Field(min_length=1)
    study_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    value: float
    source_device: str | None = None


class ParticipantImportRow(BaseModel):
    participant_id: str = Field(min_length=1)
    study_id: str = Field(min_length=1)
    status: str = Field(default="active")


class ParticipantImportRequest(BaseModel):
    import_id: str = Field(min_length=1)
    rows: list[ParticipantImportRow] = Field(min_length=1)


def validate_event(payload: EventIngest) -> None:
    # Lightweight domain rules, expanded by event-processor anomaly engine.
    if payload.event_type == "heart_rate" and not (20 <= payload.value <= 250):
        raise HTTPException(status_code=422, detail="heart_rate value out of allowed range")
    if payload.event_type == "spo2" and not (50 <= payload.value <= 100):
        raise HTTPException(status_code=422, detail="spo2 value out of allowed range")
    if payload.event_type == "temperature_c" and not (30 <= payload.value <= 45):
        raise HTTPException(status_code=422, detail="temperature value out of allowed range")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "ingestion-service"}


@app.post("/events")
def ingest_event(payload: EventIngest, x_tenant_id: str | None = Header(default=None)) -> dict[str, str]:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    if payload.tenant_id and payload.tenant_id != x_tenant_id:
        raise HTTPException(status_code=403, detail="tenant mismatch")
    tenant_id = x_tenant_id
    validate_event(payload)
    event = payload.model_dump()
    event["tenant_id"] = tenant_id
    now_epoch = datetime.now(timezone.utc).timestamp()
    event_id = event["event_id"]
    with SEEN_EVENT_IDS_LOCK:
        prune_idempotency_keys(now_epoch)
        if event_id in SEEN_EVENT_IDS:
            return {"result": "duplicate_ignored", "event_id": event_id}

    event["received_at"] = datetime.now(timezone.utc).isoformat()
    event["enriched"] = {
        "ingestion_service_version": "0.4.0",
        "ingested_epoch": int(now_epoch),
    }
    try:
        publish_event(event)
        with SEEN_EVENT_IDS_LOCK:
            SEEN_EVENT_IDS[event_id] = datetime.now(timezone.utc).timestamp()
        with BUFFER_LOCK:
            BUFFERED_EVENT_IDS.discard(event_id)
    except (KafkaError, RuntimeError, OSError, TimeoutError) as exc:
        already_buffered = buffer_event(event, event_id)
        if already_buffered:
            raise HTTPException(status_code=503, detail="event buffered locally; broker unavailable") from exc
        raise HTTPException(status_code=503, detail="event not persisted to broker; buffered locally") from exc
    return {"result": "accepted", "tenant_id": tenant_id, "event_id": event_id}


@app.post("/imports/participants")
def enqueue_participant_import(
    payload: ParticipantImportRequest,
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    producer = get_producer()
    if producer is None:
        raise HTTPException(status_code=503, detail="kafka unavailable")
    for row in payload.rows:
        message = {
            "tenant_id": x_tenant_id,
            "import_id": payload.import_id,
            "type": "participant_import",
            "participant": row.model_dump(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        producer.send(KAFKA_IMPORTS_TOPIC, message)
    producer.flush(timeout=2)
    return {"result": "queued", "tenant_id": x_tenant_id, "import_id": payload.import_id, "rows": len(payload.rows)}


@app.get("/events/stats")
def event_stats() -> dict[str, int]:
    return {"buffered_events": len(INGESTION_BUFFER), "idempotency_keys": len(SEEN_EVENT_IDS)}
