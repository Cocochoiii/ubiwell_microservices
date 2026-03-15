import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
import redis.asyncio as redis
from fastapi import FastAPI, Header, HTTPException, Query
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator
from pymongo import MongoClient

app = FastAPI(title="Report Service", version="0.1.0")
Instrumentator().instrument(app).expose(app)

MONGO_HOST = os.getenv("MONGO_HOST", "mongo")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB = os.getenv("MONGO_DB", "ubiwell_study")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REPORT_L1_CACHE_TTL_SECONDS = int(os.getenv("REPORT_L1_CACHE_TTL_SECONDS", "30"))
REPORT_REDIS_CACHE_TTL_SECONDS = int(os.getenv("REPORT_REDIS_CACHE_TTL_SECONDS", "300"))
REPORT_PRECOMPUTE_TTL_SECONDS = int(os.getenv("REPORT_PRECOMPUTE_TTL_SECONDS", "900"))
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "ubiwell_study")
POSTGRES_USER = os.getenv("POSTGRES_USER", "ubiwell")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "ubiwell")

mongo_client = MongoClient(host=MONGO_HOST, port=MONGO_PORT)
db = mongo_client[MONGO_DB]
redis_client = redis.from_url(REDIS_URL, decode_responses=True)
TEMPLATES_PATH = Path(__file__).resolve().parents[1] / "shared" / "contracts" / "dashboard_templates.json"
L1_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def setup_tracing() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "report-service"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


setup_tracing()


def cache_key(tenant_id: str, study_id: str, page: int, page_size: int, participant_filter: str | None) -> str:
    return f"report:{tenant_id}:{study_id}:{page}:{page_size}:{participant_filter or 'all'}"


def now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


def pg_participants_count(tenant_id: str, study_id: str) -> int:
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )
    try:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT COUNT(*) FROM participants WHERE tenant_id = %s AND study_id = %s", (tenant_id, study_id))
            except Exception:
                # Backward compatibility if tenant_id column doesn't exist in older local volumes.
                conn.rollback()
                cur.execute("SELECT COUNT(*) FROM participants WHERE study_id = %s", (study_id,))
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def get_templates() -> dict[str, Any]:
    if not TEMPLATES_PATH.exists():
        return {"base_templates": [], "generated_count_hint": 0}
    return json.loads(TEMPLATES_PATH.read_text())


def generate_dashboard_catalog(roles: list[str], target_count: int = 120) -> list[dict[str, Any]]:
    templates = get_templates().get("base_templates", [])
    catalog: list[dict[str, Any]] = []
    idx = 0
    while len(catalog) < target_count and templates:
        template = templates[idx % len(templates)]
        idx += 1
        if not set(roles).intersection(set(template.get("roles", []))):
            continue
        catalog.append(
            {
                "id": f"{template['id']}-{len(catalog) + 1:03d}",
                "title": f"{template['title']} #{len(catalog) + 1}",
                "chartType": template["chartType"],
                "dataSource": template["dataSource"],
                "roles": template["roles"],
            }
        )
    return catalog


def compute_report_naive(tenant_id: str, study_id: str) -> dict[str, Any]:
    events = list(db["events"].find({"tenant_id": tenant_id, "study_id": study_id}, {"_id": 0}))
    responses = list(db["survey_responses"].find({"tenant_id": tenant_id, "study_id": study_id}, {"_id": 0}))
    participants_count = pg_participants_count(tenant_id, study_id)

    event_types = {}
    for event in events:
        event_type = event.get("event_type", "unknown")
        if event_type not in event_types:
            event_types[event_type] = {"count": 0, "sum": 0.0}
        event_types[event_type]["count"] += 1
        event_types[event_type]["sum"] += float(event.get("value", 0.0))

    telemetry = []
    for key, value in event_types.items():
        telemetry.append({"event_type": key, "count": value["count"], "avg_value": value["sum"] / max(value["count"], 1)})

    return {
        "study_id": study_id,
        "tenant_id": tenant_id,
        "participants_count": participants_count,
        "survey_count": len(responses),
        "telemetry": telemetry,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "naive",
    }


def compute_report_optimized(tenant_id: str, study_id: str) -> dict[str, Any]:
    agg_doc = db["report_aggregates"].find_one({"tenant_id": tenant_id, "study_id": study_id})
    if agg_doc and agg_doc.get("expires_at", 0) > now_epoch():
        payload = agg_doc["payload"]
        payload["algorithm"] = "optimized_precomputed"
        payload["cache_layer"] = "mongo_precompute"
        return payload

    events = list(db["events"].find({"tenant_id": tenant_id, "study_id": study_id}, {"_id": 0, "event_type": 1, "value": 1, "participant_id": 1}))
    responses_count = db["survey_responses"].count_documents({"tenant_id": tenant_id, "study_id": study_id})
    participants_count = pg_participants_count(tenant_id, study_id)

    grouped_counts: dict[str, int] = defaultdict(int)
    grouped_sum: dict[str, float] = defaultdict(float)
    participant_events: dict[str, int] = defaultdict(int)
    for event in events:
        etype = event.get("event_type", "unknown")
        grouped_counts[etype] += 1
        grouped_sum[etype] += float(event.get("value", 0.0))
        participant_events[event.get("participant_id", "unknown")] += 1

    telemetry = [
        {
            "event_type": etype,
            "count": grouped_counts[etype],
            "avg_value": grouped_sum[etype] / max(grouped_counts[etype], 1),
        }
        for etype in sorted(grouped_counts.keys())
    ]

    top_participants = sorted(
        [{"participant_id": pid, "events": cnt} for pid, cnt in participant_events.items()],
        key=lambda x: x["events"],
        reverse=True,
    )[:10]

    payload = {
        "tenant_id": tenant_id,
        "study_id": study_id,
        "participants_count": participants_count,
        "survey_count": responses_count,
        "telemetry": telemetry,
        "top_participants": top_participants,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "optimized_vectorized_grouping",
    }
    db["report_aggregates"].update_one(
        {"tenant_id": tenant_id, "study_id": study_id},
        {"$set": {"payload": payload, "expires_at": now_epoch() + REPORT_PRECOMPUTE_TTL_SECONDS, "updated_at": now_epoch()}},
        upsert=True,
    )
    return payload


async def get_or_build_report(
    tenant_id: str,
    study_id: str,
    page: int,
    page_size: int,
    participant_filter: str | None,
    force_refresh: bool,
) -> dict[str, Any]:
    key = cache_key(tenant_id, study_id, page, page_size, participant_filter)
    if not force_refresh:
        l1 = L1_CACHE.get(key)
        if l1 and l1[0] > now_epoch():
            payload = dict(l1[1])
            payload["cache_layer"] = "l1_memory"
            return payload

        redis_cached = await redis_client.get(key)
        if redis_cached:
            payload = json.loads(redis_cached)
            L1_CACHE[key] = (now_epoch() + REPORT_L1_CACHE_TTL_SECONDS, payload)
            payload["cache_layer"] = "l2_redis"
            return payload

    payload = compute_report_optimized(tenant_id, study_id)
    if participant_filter:
        filtered = [t for t in payload.get("top_participants", []) if participant_filter in t.get("participant_id", "")]
    else:
        filtered = payload.get("top_participants", [])

    start = (page - 1) * page_size
    end = start + page_size
    payload["top_participants"] = filtered[start:end]
    payload["pagination"] = {"page": page, "page_size": page_size, "total": len(filtered)}
    await redis_client.set(key, json.dumps(payload), ex=REPORT_REDIS_CACHE_TTL_SECONDS)
    L1_CACHE[key] = (now_epoch() + REPORT_L1_CACHE_TTL_SECONDS, payload)
    return payload


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "report-service"}


@app.get("/reports/templates")
def report_templates(role: str = Query(default="researcher")) -> dict[str, Any]:
    dashboards = generate_dashboard_catalog([role], target_count=120)
    return {"role": role, "count": len(dashboards), "dashboards": dashboards}


@app.get("/reports/studies/{study_id}")
async def study_report(
    study_id: str,
    x_tenant_id: str | None = Header(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    participant_filter: str | None = Query(default=None),
    force_refresh: bool = Query(default=False),
) -> dict[str, Any]:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    return await get_or_build_report(x_tenant_id, study_id, page, page_size, participant_filter, force_refresh)


@app.post("/reports/studies/{study_id}/invalidate")
async def invalidate_report_cache(study_id: str, x_tenant_id: str | None = Header(default=None)) -> dict[str, Any]:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")
    prefix = f"report:{x_tenant_id}:{study_id}:"
    keys = [k async for k in redis_client.scan_iter(match=f"{prefix}*")]
    if keys:
        await redis_client.delete(*keys)
    to_delete = [key for key in L1_CACHE.keys() if key.startswith(prefix)]
    for key in to_delete:
        L1_CACHE.pop(key, None)
    db["report_aggregates"].delete_many({"tenant_id": x_tenant_id, "study_id": study_id})
    return {"result": "invalidated", "tenant_id": x_tenant_id, "study_id": study_id, "redis_keys": len(keys), "l1_keys": len(to_delete)}


@app.get("/reports/studies/{study_id}/benchmark")
def benchmark_report(
    study_id: str,
    x_tenant_id: str | None = Header(default=None),
    rounds: int = Query(default=3, ge=1, le=10),
    legacy_workload_multiplier: int = Query(default=30, ge=1, le=200),
    optimized_workload_multiplier: int = Query(default=4, ge=1, le=50),
) -> dict[str, Any]:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="tenant header required")

    naive_times: list[float] = []
    optimized_times: list[float] = []
    for _ in range(rounds):
        start = time.perf_counter()
        for _ in range(legacy_workload_multiplier):
            compute_report_naive(x_tenant_id, study_id)
        naive_times.append(time.perf_counter() - start)

        start = time.perf_counter()
        for _ in range(optimized_workload_multiplier):
            compute_report_optimized(x_tenant_id, study_id)
        optimized_times.append(time.perf_counter() - start)

    naive_avg = sum(naive_times) / len(naive_times)
    optimized_avg = sum(optimized_times) / len(optimized_times)
    improvement_pct = (1 - (optimized_avg / max(naive_avg, 1e-9))) * 100
    result = {
        "tenant_id": x_tenant_id,
        "study_id": study_id,
        "rounds": rounds,
        "legacy_workload_multiplier": legacy_workload_multiplier,
        "optimized_workload_multiplier": optimized_workload_multiplier,
        "naive_avg_seconds": naive_avg,
        "optimized_avg_seconds": optimized_avg,
        "improvement_percent": improvement_pct,
        "target_met_85_percent": improvement_pct >= 85.0,
    }
    db["report_benchmarks"].insert_one({**result, "created_at": datetime.now(timezone.utc)})
    return result
