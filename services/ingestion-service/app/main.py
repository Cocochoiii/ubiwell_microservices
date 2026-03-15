import json
import os
import threading
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

PRODUCER = None
SEEN_EVENT_IDS: dict[str, float] = {}
SEEN_EVENT_IDS_LOCK = threading.Lock()


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
    except KafkaError:
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
    except Exception:
        # Topic bootstrap is best-effort in local dev.
        pass


@app.on_event("startup")
def startup() -> None:
    ensure_topics()


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
    tenant_id = payload.tenant_id or x_tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")
    validate_event(payload)
    event = payload.model_dump()
    event["tenant_id"] = tenant_id
    now_epoch = datetime.now(timezone.utc).timestamp()
    event_id = event["event_id"]
    with SEEN_EVENT_IDS_LOCK:
        stale_ids = [
            key for key, ts in SEEN_EVENT_IDS.items() if now_epoch - ts > IDEMPOTENCY_WINDOW_SECONDS
        ]
        for key in stale_ids:
            SEEN_EVENT_IDS.pop(key, None)

        if event_id in SEEN_EVENT_IDS:
            return {"result": "duplicate_ignored", "event_id": event_id}
        SEEN_EVENT_IDS[event_id] = now_epoch

    event["received_at"] = datetime.now(timezone.utc).isoformat()
    event["enriched"] = {
        "ingestion_service_version": "0.4.0",
        "ingested_epoch": int(now_epoch),
    }
    producer = get_producer()
    try:
        if producer is None:
            raise RuntimeError("kafka producer unavailable")
        producer.send(KAFKA_EVENTS_TOPIC, event)
        producer.flush(timeout=1)
    except Exception:
        # Keep a local fallback buffer if broker is temporarily unavailable.
        INGESTION_BUFFER.append(event)
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
