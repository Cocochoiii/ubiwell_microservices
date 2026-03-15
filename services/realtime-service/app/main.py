import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import jwt
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator
from pymongo import MongoClient

app = FastAPI(title="Realtime Service", version="0.1.0")
Instrumentator().instrument(app).expose(app)

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me-to-32-plus-bytes")
JWT_ALGORITHM = "HS256"
MONGO_HOST = os.getenv("MONGO_HOST", "mongo")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB = os.getenv("MONGO_DB", "ubiwell_study")

mongo = MongoClient(host=MONGO_HOST, port=MONGO_PORT)
db = mongo[MONGO_DB]


def setup_tracing() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "realtime-service"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


setup_tracing()


def parse_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc


def role_allowed(role: str, widget: str) -> bool:
    if role == "admin":
        return True
    if role == "researcher":
        return widget != "critical_alerts_only"
    if role == "clinician":
        return widget in {"alerts", "telemetry", "critical_alerts_only"}
    return False


def get_snapshot(tenant_id: str, study_id: str, role: str) -> dict[str, Any]:
    alert_query = {"tenant_id": tenant_id, "study_id": study_id}
    alerts_total = db["alerts"].count_documents(alert_query)
    critical_alerts = db["alerts"].count_documents({**alert_query, "severity": "critical"})
    telemetry_count = db["events"].count_documents({"tenant_id": tenant_id, "study_id": study_id})

    payload = {
        "tenant_id": tenant_id,
        "study_id": study_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "role": role,
        "widgets": {},
    }
    if role_allowed(role, "alerts"):
        payload["widgets"]["alerts"] = {"total": alerts_total, "critical": critical_alerts}
    if role_allowed(role, "telemetry"):
        payload["widgets"]["telemetry"] = {"events": telemetry_count}
    if role_allowed(role, "critical_alerts_only"):
        payload["widgets"]["critical_alerts_only"] = {"critical": critical_alerts}
    return payload


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "realtime-service"}


@app.websocket("/ws/studies/{study_id}")
async def stream_study(websocket: WebSocket, study_id: str) -> None:
    token = websocket.query_params.get("token")
    tenant_id = websocket.query_params.get("tenant_id")
    if not token or not tenant_id:
        await websocket.close(code=1008)
        return

    try:
        claims = parse_token(token)
    except HTTPException:
        await websocket.close(code=1008)
        return
    if claims.get("tenant_id") != tenant_id:
        await websocket.close(code=1008)
        return
    role = claims.get("role", "researcher")

    await websocket.accept()
    try:
        while True:
            snapshot = get_snapshot(tenant_id=tenant_id, study_id=study_id, role=role)
            await websocket.send_json(snapshot)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
