import os
from datetime import datetime, timezone

import grpc
import pybreaker
import study_workflow_pb2
import study_workflow_pb2_grpc
from fastapi import FastAPI, Header, HTTPException
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator
from pymongo import MongoClient

app = FastAPI(title="Analytics Service", version="0.4.0")
Instrumentator().instrument(app).expose(app)

PARTICIPANT_SERVICE_URL = os.getenv("PARTICIPANT_SERVICE_URL", "http://participant-service:8001")
SURVEY_SERVICE_URL = os.getenv("SURVEY_SERVICE_URL", "http://survey-service:8002")
PARTICIPANT_GRPC_HOST = os.getenv("PARTICIPANT_GRPC_HOST", "participant-service")
PARTICIPANT_GRPC_PORT = int(os.getenv("PARTICIPANT_GRPC_PORT", "50051"))
SURVEY_GRPC_HOST = os.getenv("SURVEY_GRPC_HOST", "survey-service")
SURVEY_GRPC_PORT = int(os.getenv("SURVEY_GRPC_PORT", "50052"))
MONGO_HOST = os.getenv("MONGO_HOST", "mongo")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB = os.getenv("MONGO_DB", "ubiwell_study")

mongo_client = MongoClient(host=MONGO_HOST, port=MONGO_PORT)
db = mongo_client[MONGO_DB]
breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=20)


def setup_tracing() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "analytics-service"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


setup_tracing()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "analytics-service"}


@breaker
def _get_participant_count(tenant_id: str, study_id: str) -> int:
    with grpc.insecure_channel(f"{PARTICIPANT_GRPC_HOST}:{PARTICIPANT_GRPC_PORT}") as participant_channel:
        participant_stub = study_workflow_pb2_grpc.ParticipantServiceStub(participant_channel)
        participant_resp = participant_stub.GetParticipantCountByStudy(
            study_workflow_pb2.GetParticipantCountByStudyRequest(tenant_id=tenant_id, study_id=study_id)
        )
    return int(participant_resp.count)


@breaker
def _get_survey_count(tenant_id: str, study_id: str) -> int:
    with grpc.insecure_channel(f"{SURVEY_GRPC_HOST}:{SURVEY_GRPC_PORT}") as survey_channel:
        survey_stub = study_workflow_pb2_grpc.SurveyServiceStub(survey_channel)
        survey_resp = survey_stub.GetSurveyResponseCount(
            study_workflow_pb2.GetSurveyResponseCountRequest(tenant_id=tenant_id, study_id=study_id)
        )
    return int(survey_resp.count)


def with_retries(func, *args) -> int:
    last_error = None
    for _ in range(3):
        try:
            return int(func(*args))
        except Exception as exc:
            last_error = exc
    raise HTTPException(status_code=503, detail=f"upstream unavailable: {last_error}")


@app.get("/studies/{study_id}/summary")
def study_summary(study_id: str, x_tenant_id: str | None = Header(default=None)) -> dict[str, object]:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    participant_count = with_retries(_get_participant_count, x_tenant_id, study_id)
    survey_count = with_retries(_get_survey_count, x_tenant_id, study_id)
    telemetry = db["event_aggregates"].find_one({"tenant_id": x_tenant_id, "study_id": study_id}, {"_id": 0}) or {}

    return {
        "tenant_id": x_tenant_id,
        "study_id": study_id,
        "participants": participant_count,
        "survey_responses": survey_count,
        "events": telemetry.get("event_count", 0),
        "sources": ["grpc:participant-service", "grpc:survey-service"],
        "status": "ok",
    }


@app.get("/studies/{study_id}/alerts")
def get_study_alerts(study_id: str, x_tenant_id: str | None = Header(default=None)) -> list[dict]:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    cursor = db["alerts"].find({"tenant_id": x_tenant_id, "study_id": study_id}, {"_id": 0}).sort("created_at", -1).limit(200)
    return list(cursor)


@app.get("/studies/{study_id}/telemetry/summary")
def telemetry_summary(study_id: str, x_tenant_id: str | None = Header(default=None)) -> dict:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    pipeline = [
        {"$match": {"tenant_id": x_tenant_id, "study_id": study_id}},
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}, "avg_value": {"$avg": "$value"}}},
    ]
    groups = list(db["events"].aggregate(pipeline))
    return {"tenant_id": x_tenant_id, "study_id": study_id, "metrics_by_event_type": groups}


@app.get("/studies/{study_id}/report")
def generate_report(study_id: str, x_tenant_id: str | None = Header(default=None)) -> dict:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    summary = study_summary(study_id=study_id, x_tenant_id=x_tenant_id)
    alerts = get_study_alerts(study_id=study_id, x_tenant_id=x_tenant_id)
    telemetry = telemetry_summary(study_id=study_id, x_tenant_id=x_tenant_id)
    return {
        "tenant_id": x_tenant_id,
        "study_id": study_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "alerts_count": len(alerts),
        "telemetry_summary": telemetry,
    }
