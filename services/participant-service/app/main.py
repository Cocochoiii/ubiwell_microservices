import os
import threading
from concurrent import futures
from datetime import datetime, timezone
from typing import Any

import grpc
import psycopg2
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

app = FastAPI(title="Participant Service", version="0.4.0")
Instrumentator().instrument(app).expose(app)

PARTICIPANT_GRPC_PORT = int(os.getenv("PARTICIPANT_GRPC_PORT", "50051"))


class ParticipantCreate(BaseModel):
    tenant_id: str | None = None
    participant_id: str = Field(min_length=1)
    study_id: str = Field(min_length=1)
    status: str = Field(default="active")


class ParticipantImport(BaseModel):
    participants: list[ParticipantCreate] = Field(min_length=1)


def setup_tracing() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "participant-service"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


setup_tracing()


def get_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "ubiwell_study"),
        user=os.getenv("POSTGRES_USER", "ubiwell"),
        password=os.getenv("POSTGRES_PASSWORD", "ubiwell"),
    )


class ParticipantGrpcServicer(study_workflow_pb2_grpc.ParticipantServiceServicer):
    def GetParticipant(self, request, context):
        tenant_id = request.tenant_id
        participant_id = request.participant_id
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT tenant_id, participant_id, study_id, status FROM participants WHERE tenant_id = %s AND participant_id = %s",
                    (tenant_id, participant_id),
                )
                row = cur.fetchone()

        if not row:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("participant not found")
            return study_workflow_pb2.ParticipantResponse()

        return study_workflow_pb2.ParticipantResponse(
            tenant_id=row[0],
            participant_id=row[1],
            study_id=row[2],
            status=row[3],
        )

    def GetParticipantCountByStudy(self, request, context):
        tenant_id = request.tenant_id
        study_id = request.study_id
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM participants WHERE tenant_id = %s AND study_id = %s", (tenant_id, study_id))
                count = cur.fetchone()[0]

        return study_workflow_pb2.ParticipantCountByStudyResponse(
            tenant_id=tenant_id,
            study_id=study_id,
            count=count,
        )


def run_grpc_server():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    study_workflow_pb2_grpc.add_ParticipantServiceServicer_to_server(ParticipantGrpcServicer(), server)
    server.add_insecure_port(f"[::]:{PARTICIPANT_GRPC_PORT}")
    server.start()
    server.wait_for_termination()


@app.on_event("startup")
def startup_grpc() -> None:
    thread = threading.Thread(target=run_grpc_server, daemon=True)
    thread.start()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "participant-service"}


@app.post("/participants")
def create_participant(payload: ParticipantCreate, x_tenant_id: str | None = Header(default=None)) -> dict[str, str]:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    if payload.tenant_id and payload.tenant_id != x_tenant_id:
        raise HTTPException(status_code=403, detail="tenant mismatch")
    tenant_id = x_tenant_id
    query = """
    INSERT INTO participants (tenant_id, participant_id, study_id, status)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (tenant_id, participant_id) DO UPDATE
      SET study_id = EXCLUDED.study_id,
          status = EXCLUDED.status
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (tenant_id, payload.participant_id, payload.study_id, payload.status))
            conn.commit()
    return {"result": "upserted", "tenant_id": tenant_id, "participant_id": payload.participant_id}


@app.post("/participants/import")
async def import_participants(payload: ParticipantImport, x_tenant_id: str | None = Header(default=None)) -> dict[str, Any]:
    tenant_id = x_tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    processed = 0
    for participant in payload.participants:
        body = participant.model_dump()
        body["tenant_id"] = tenant_id
        create_participant(ParticipantCreate(**body), x_tenant_id=tenant_id)
        processed += 1
    return {"result": "imported", "tenant_id": tenant_id, "processed": processed}


@app.get("/participants")
def list_participants(x_tenant_id: str | None = Header(default=None)) -> list[dict[str, str]]:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id, participant_id, study_id, status FROM participants WHERE tenant_id = %s ORDER BY id DESC LIMIT 500",
                (x_tenant_id,),
            )
            rows = cur.fetchall()
    return [{"tenant_id": row[0], "participant_id": row[1], "study_id": row[2], "status": row[3]} for row in rows]


@app.get("/participants/{participant_id}")
def get_participant(participant_id: str, x_tenant_id: str | None = Header(default=None)) -> dict[str, str]:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id, participant_id, study_id, status FROM participants WHERE tenant_id = %s AND participant_id = %s",
                (x_tenant_id, participant_id),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="participant not found")
    return {"tenant_id": row[0], "participant_id": row[1], "study_id": row[2], "status": row[3]}


@app.get("/studies/{study_id}/tasks")
def list_study_tasks(study_id: str, x_tenant_id: str | None = Header(default=None)) -> list[dict[str, Any]]:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, task_name, assignee, status, created_at FROM tasks WHERE tenant_id = %s AND study_id = %s ORDER BY id DESC LIMIT 200",
                (x_tenant_id, study_id),
            )
            rows = cur.fetchall()
    return [
        {
            "id": row[0],
            "task_name": row[1],
            "assignee": row[2],
            "status": row[3],
            "created_at": row[4].isoformat() if row[4] else datetime.now(timezone.utc).isoformat(),
        }
        for row in rows
    ]
