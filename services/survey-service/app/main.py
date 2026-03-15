import os
import threading
from concurrent import futures
from datetime import datetime, timezone
from typing import Any

import grpc
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
from pydantic import BaseModel, Field
from pymongo import MongoClient

app = FastAPI(title="Survey Service", version="0.4.0")
Instrumentator().instrument(app).expose(app)

SURVEY_GRPC_PORT = int(os.getenv("SURVEY_GRPC_PORT", "50052"))


class SurveyResponseCreate(BaseModel):
    tenant_id: str | None = None
    study_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    survey_id: str = Field(min_length=1)
    answers: dict[str, Any]


def setup_tracing() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "survey-service"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


setup_tracing()


def get_collection():
    host = os.getenv("MONGO_HOST", "mongo")
    port = int(os.getenv("MONGO_PORT", "27017"))
    db_name = os.getenv("MONGO_DB", "ubiwell_study")
    client = MongoClient(host=host, port=port)
    return client[db_name]["survey_responses"]


class SurveyGrpcServicer(study_workflow_pb2_grpc.SurveyServiceServicer):
    def GetSurveyResponseCount(self, request, context):
        tenant_id = request.tenant_id
        study_id = request.study_id
        count = get_collection().count_documents({"tenant_id": tenant_id, "study_id": study_id})
        return study_workflow_pb2.SurveyResponseCountResponse(tenant_id=tenant_id, study_id=study_id, count=count)


def run_grpc_server():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    study_workflow_pb2_grpc.add_SurveyServiceServicer_to_server(SurveyGrpcServicer(), server)
    server.add_insecure_port(f"[::]:{SURVEY_GRPC_PORT}")
    server.start()
    server.wait_for_termination()


@app.on_event("startup")
def startup_grpc() -> None:
    thread = threading.Thread(target=run_grpc_server, daemon=True)
    thread.start()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "survey-service"}


@app.post("/responses")
def create_response(payload: SurveyResponseCreate, x_tenant_id: str | None = Header(default=None)) -> dict[str, str]:
    tenant_id = payload.tenant_id or x_tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")
    doc = {
        "tenant_id": tenant_id,
        "study_id": payload.study_id,
        "participant_id": payload.participant_id,
        "survey_id": payload.survey_id,
        "answers": payload.answers,
        "created_at": datetime.now(timezone.utc),
    }
    get_collection().insert_one(doc)
    return {"result": "created", "tenant_id": tenant_id}


@app.get("/responses/count/{study_id}")
def get_study_response_count(study_id: str, x_tenant_id: str | None = Header(default=None)) -> dict[str, int | str]:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    count = get_collection().count_documents({"tenant_id": x_tenant_id, "study_id": study_id})
    return {"tenant_id": x_tenant_id, "study_id": study_id, "count": count}


@app.get("/responses/study/{study_id}")
def list_study_responses(study_id: str, x_tenant_id: str | None = Header(default=None)) -> list[dict[str, Any]]:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    cursor = get_collection().find({"tenant_id": x_tenant_id, "study_id": study_id}, {"_id": 0}).sort("created_at", -1).limit(500)
    return list(cursor)
