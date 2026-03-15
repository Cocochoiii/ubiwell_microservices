import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import jwt
import redis.asyncio as redis
import bcrypt
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from pymongo import MongoClient

app = FastAPI(title="API Gateway", version="0.4.0")
logger = logging.getLogger(__name__)

PARTICIPANT_SERVICE_URL = os.getenv("PARTICIPANT_SERVICE_URL", "http://participant-service:8001")
SURVEY_SERVICE_URL = os.getenv("SURVEY_SERVICE_URL", "http://survey-service:8002")
INGESTION_SERVICE_URL = os.getenv("INGESTION_SERVICE_URL", "http://ingestion-service:8003")
ANALYTICS_SERVICE_URL = os.getenv("ANALYTICS_SERVICE_URL", "http://analytics-service:8004")
REPORT_SERVICE_URL = os.getenv("REPORT_SERVICE_URL", "http://report-service:8005")
REALTIME_SERVICE_URL = os.getenv("REALTIME_SERVICE_URL", "http://realtime-service:8006")
COLLECTOR_SERVICE_URL = os.getenv("COLLECTOR_SERVICE_URL", "http://collector-service:8007")
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRES_MINUTES = int(os.getenv("TOKEN_EXPIRES_MINUTES", "240"))
TOKEN_EXPIRES_MINUTES_PROD = int(os.getenv("TOKEN_EXPIRES_MINUTES_PROD", "30"))
APP_ENV = os.getenv("APP_ENV", "demo")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
TENANT_RATE_LIMIT_PER_MINUTE = int(os.getenv("TENANT_RATE_LIMIT_PER_MINUTE", "1200"))
MONGO_HOST = os.getenv("MONGO_HOST", "mongo")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB = os.getenv("MONGO_DB", "ubiwell_study")

USERS_JSON = os.getenv("AUTH_USERS_JSON")


def validate_security_config() -> None:
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET must be set")
    if len(JWT_SECRET) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters")
    if not USERS_JSON:
        raise RuntimeError("AUTH_USERS_JSON must be set")


def normalize_users(users_json: str) -> dict[str, dict[str, Any]]:
    users: dict[str, dict[str, Any]] = {}
    for item in json.loads(users_json):
        record = dict(item)
        if "password_hash" not in record:
            raw = record.pop("password", None)
            if raw:
                record["password_hash"] = bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        if "password_hash" not in record:
            raise ValueError(f"user '{record.get('username', 'unknown')}' is missing password or password_hash")
        users[record["username"]] = record
    return users


validate_security_config()
USERS = normalize_users(USERS_JSON or "")

redis_client = redis.from_url(REDIS_URL, decode_responses=True)
mongo_client = MongoClient(host=MONGO_HOST, port=MONGO_PORT)
audit_collection = mongo_client[MONGO_DB]["audit_logs"]

Instrumentator().instrument(app).expose(app)


def setup_tracing() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "api-gateway"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


setup_tracing()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class ParticipantCreate(BaseModel):
    participant_id: str = Field(min_length=1)
    study_id: str = Field(min_length=1)
    status: str = Field(default="active")


class SurveyResponseCreate(BaseModel):
    study_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    survey_id: str = Field(min_length=1)
    answers: dict[str, Any]


class EventIngest(BaseModel):
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


class APICollectRequest(BaseModel):
    study_id: str = Field(default="study-a", min_length=1)
    source_name: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    hours: int = Field(default=24, ge=1, le=720)
    points_per_minute: int = Field(default=1, ge=1, le=16)


class WebCollectRequest(BaseModel):
    study_id: str = Field(default="study-a", min_length=1)
    source_name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    css_selector: str = Field(default="body")
    use_selenium: bool = False
    max_points: int = Field(default=100, ge=1, le=10000)


def create_access_token(username: str, role: str, tenant_id: str) -> str:
    ttl_minutes = TOKEN_EXPIRES_MINUTES if APP_ENV == "demo" else TOKEN_EXPIRES_MINUTES_PROD
    payload = {
        "sub": username,
        "role": role,
        "tenant_id": tenant_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_bearer_token(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.replace("Bearer ", "", 1).strip()
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc


async def enforce_tenant_rate_limit(tenant_id: str) -> None:
    bucket = int(time.time() // 60)
    key = f"ratelimit:{tenant_id}:{bucket}"
    current = await redis_client.incr(key)
    if current == 1:
        await redis_client.expire(key, 65)
    if current > TENANT_RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="tenant rate limit exceeded")


async def authenticate(
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    claims = decode_bearer_token(authorization)
    token_tenant_id = claims.get("tenant_id")
    if not token_tenant_id or not x_tenant_id:
        raise HTTPException(status_code=401, detail="tenant context required")
    if token_tenant_id != x_tenant_id:
        raise HTTPException(status_code=403, detail="tenant mismatch")
    await enforce_tenant_rate_limit(token_tenant_id)
    return claims


def require_role(claims: dict[str, Any], allowed: set[str]) -> None:
    role = claims.get("role")
    if role not in allowed:
        raise HTTPException(status_code=403, detail="insufficient role")


async def write_audit_log(request: Request, claims: dict[str, Any], action: str, status: int) -> None:
    doc = {
        "tenant_id": claims.get("tenant_id"),
        "username": claims.get("sub"),
        "role": claims.get("role"),
        "action": action,
        "path": request.url.path,
        "method": request.method,
        "status": status,
        "ts": datetime.now(timezone.utc),
    }
    try:
        await asyncio.to_thread(audit_collection.insert_one, doc)
    except Exception as exc:
        logger.warning("Failed to write audit log for action %s: %s", action, exc)


async def proxy_get(url: str, tenant_id: str) -> Any:
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(url, headers={"x-tenant-id": tenant_id})
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()


async def proxy_get_with_params(url: str, tenant_id: str, params: dict[str, Any]) -> Any:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, params=params, headers={"x-tenant-id": tenant_id})
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()


async def proxy_post(url: str, tenant_id: str, payload: dict[str, Any]) -> Any:
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.post(url, json=payload, headers={"x-tenant-id": tenant_id})
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "api-gateway"}


@app.post("/auth/token")
async def issue_token(payload: LoginRequest) -> dict[str, str]:
    user = USERS.get(payload.username)
    if not user:
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not bcrypt.checkpw(payload.password.encode("utf-8"), user.get("password_hash", "").encode("utf-8")):
        raise HTTPException(status_code=401, detail="invalid credentials")

    token = create_access_token(payload.username, user["role"], user["tenant_id"])
    return {"access_token": token, "token_type": "bearer"}


@app.get("/participants")
async def list_participants(
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> Any:
    require_role(claims, {"admin", "researcher", "clinician"})
    cache_key = f"cache:participants:{x_tenant_id}"
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    response = await proxy_get(f"{PARTICIPANT_SERVICE_URL}/participants", tenant_id=x_tenant_id or "")
    await redis_client.set(cache_key, json.dumps(response), ex=20)
    return response


@app.post("/participants")
async def create_participant(
    payload: ParticipantCreate,
    request: Request,
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> Any:
    require_role(claims, {"admin", "researcher"})
    response = await proxy_post(
        f"{PARTICIPANT_SERVICE_URL}/participants",
        tenant_id=x_tenant_id or "",
        payload=payload.model_dump(),
    )
    await redis_client.delete(f"cache:participants:{x_tenant_id}")
    await write_audit_log(request, claims, "create_participant", 200)
    return response


@app.post("/survey/responses")
async def submit_response(
    payload: SurveyResponseCreate,
    request: Request,
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> Any:
    require_role(claims, {"admin", "researcher", "clinician"})
    response = await proxy_post(f"{SURVEY_SERVICE_URL}/responses", tenant_id=x_tenant_id or "", payload=payload.model_dump())
    await write_audit_log(request, claims, "submit_survey_response", 200)
    return response


@app.post("/events")
async def ingest_event(
    payload: EventIngest,
    request: Request,
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> Any:
    require_role(claims, {"admin", "researcher", "clinician"})
    response = await proxy_post(f"{INGESTION_SERVICE_URL}/events", tenant_id=x_tenant_id or "", payload=payload.model_dump())
    await write_audit_log(request, claims, "ingest_event", 200)
    return response


@app.post("/imports/participants")
async def import_participants(
    payload: ParticipantImportRequest,
    request: Request,
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> Any:
    require_role(claims, {"admin", "researcher"})
    response = await proxy_post(
        f"{INGESTION_SERVICE_URL}/imports/participants",
        tenant_id=x_tenant_id or "",
        payload=payload.model_dump(),
    )
    await write_audit_log(request, claims, "import_participants", 200)
    return response


@app.get("/analytics/studies/{study_id}/summary")
async def get_study_summary(
    study_id: str,
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> Any:
    require_role(claims, {"admin", "researcher", "clinician"})
    return await proxy_get(f"{ANALYTICS_SERVICE_URL}/studies/{study_id}/summary", tenant_id=x_tenant_id or "")


@app.get("/analytics/studies/{study_id}/alerts")
async def get_study_alerts(
    study_id: str,
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> Any:
    require_role(claims, {"admin", "researcher", "clinician"})
    return await proxy_get(f"{ANALYTICS_SERVICE_URL}/studies/{study_id}/alerts", tenant_id=x_tenant_id or "")


@app.get("/analytics/studies/{study_id}/report")
async def get_study_report(
    study_id: str,
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> Any:
    require_role(claims, {"admin", "researcher"})
    return await proxy_get(f"{ANALYTICS_SERVICE_URL}/studies/{study_id}/report", tenant_id=x_tenant_id or "")


@app.get("/reports/templates")
async def get_report_templates(
    role: str = "researcher",
    claims: dict[str, Any] = Depends(authenticate),
) -> Any:
    require_role(claims, {"admin", "researcher", "clinician"})
    return await proxy_get_with_params(f"{REPORT_SERVICE_URL}/reports/templates", tenant_id=claims["tenant_id"], params={"role": role})


@app.get("/reports/studies/{study_id}")
async def get_report(
    study_id: str,
    page: int = 1,
    page_size: int = 25,
    participant_filter: str | None = None,
    force_refresh: bool = False,
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> Any:
    require_role(claims, {"admin", "researcher", "clinician"})
    return await proxy_get_with_params(
        f"{REPORT_SERVICE_URL}/reports/studies/{study_id}",
        tenant_id=x_tenant_id or "",
        params={
            "page": page,
            "page_size": page_size,
            "participant_filter": participant_filter,
            "force_refresh": str(force_refresh).lower(),
        },
    )


@app.get("/reports/studies/{study_id}/benchmark")
async def benchmark_report(
    study_id: str,
    rounds: int = 3,
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> Any:
    require_role(claims, {"admin", "researcher"})
    return await proxy_get_with_params(
        f"{REPORT_SERVICE_URL}/reports/studies/{study_id}/benchmark",
        tenant_id=x_tenant_id or "",
        params={"rounds": rounds},
    )


@app.post("/reports/studies/{study_id}/invalidate")
async def invalidate_report_cache(
    study_id: str,
    request: Request,
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> Any:
    require_role(claims, {"admin", "researcher"})
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.post(
            f"{REPORT_SERVICE_URL}/reports/studies/{study_id}/invalidate",
            headers={"x-tenant-id": x_tenant_id or ""},
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        payload = response.json()
    await write_audit_log(request, claims, "invalidate_report_cache", 200)
    return payload


@app.get("/realtime/ws-url")
async def realtime_ws_url(
    study_id: str,
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, str]:
    require_role(claims, {"admin", "researcher", "clinician"})
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    token = create_access_token(claims["sub"], claims["role"], claims["tenant_id"])
    return {
        "ws_url": f"ws://localhost:8006/ws/studies/{study_id}?tenant_id={x_tenant_id}&token={token}",
        "service_url": REALTIME_SERVICE_URL,
    }


@app.get("/audit/logs")
async def list_audit_logs(
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    require_role(claims, {"admin"})
    docs = list(audit_collection.find({"tenant_id": x_tenant_id}, {"_id": 0}).sort("ts", -1).limit(200))
    return docs


@app.post("/pipeline/collect/api")
async def collect_pipeline_api(
    payload: APICollectRequest,
    request: Request,
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> Any:
    require_role(claims, {"admin", "researcher"})
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    response = await proxy_post(
        f"{COLLECTOR_SERVICE_URL}/pipeline/collect/api",
        tenant_id=x_tenant_id,
        payload={**payload.model_dump(), "tenant_id": x_tenant_id},
    )
    await write_audit_log(request, claims, "collect_pipeline_api", 200)
    return response


@app.post("/pipeline/collect/web")
async def collect_pipeline_web(
    payload: WebCollectRequest,
    request: Request,
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> Any:
    require_role(claims, {"admin", "researcher"})
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    response = await proxy_post(
        f"{COLLECTOR_SERVICE_URL}/pipeline/collect/web",
        tenant_id=x_tenant_id,
        payload={**payload.model_dump(), "tenant_id": x_tenant_id},
    )
    await write_audit_log(request, claims, "collect_pipeline_web", 200)
    return response


@app.post("/pipeline/collect/simulate-500h")
async def collect_pipeline_500h(
    request: Request,
    claims: dict[str, Any] = Depends(authenticate),
    x_tenant_id: str | None = Header(default=None),
) -> Any:
    require_role(claims, {"admin", "researcher"})
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{COLLECTOR_SERVICE_URL}/pipeline/collect/simulate-500h",
            params={"tenant_id": x_tenant_id, "study_id": "study-a", "source_name": "wearable-sim"},
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        payload = response.json()
    await write_audit_log(request, claims, "collect_pipeline_500h", 200)
    return payload
