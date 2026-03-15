import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from pymongo import MongoClient
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

app = FastAPI(title="Collector Service", version="0.1.0")
Instrumentator().instrument(app).expose(app)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
KAFKA_PIPELINE_TOPIC = os.getenv("KAFKA_PIPELINE_TOPIC", "patient-monitoring-raw")
KAFKA_PIPELINE_DLQ_TOPIC = os.getenv("KAFKA_PIPELINE_DLQ_TOPIC", "patient-monitoring-dlq")
SELENIUM_REMOTE_URL = os.getenv("SELENIUM_REMOTE_URL", "").strip()
MONGO_HOST = os.getenv("MONGO_HOST", "mongo")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB = os.getenv("MONGO_DB", "ubiwell_study")

if TYPE_CHECKING:
    from kafka import KafkaProducer


PRODUCER: "KafkaProducer | None" = None
MONGO = MongoClient(host=MONGO_HOST, port=MONGO_PORT)
DB = MONGO[MONGO_DB]


def setup_tracing() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "collector-service"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


setup_tracing()


def get_producer() -> "KafkaProducer":
    global PRODUCER
    if PRODUCER:
        return PRODUCER
    from kafka import KafkaProducer

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
    return PRODUCER


class APICollectRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    study_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    endpoint: str = Field(default="https://example.com")
    hours: int = Field(default=24, ge=1, le=720)
    points_per_minute: int = Field(default=1, ge=1, le=16)


class WebCollectRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    study_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    css_selector: str = Field(default="body")
    use_selenium: bool = False
    max_points: int = Field(default=100, ge=1, le=10000)


def deterministic_value(seed: str, idx: int) -> float:
    digest = hashlib.sha256(f"{seed}:{idx}".encode("utf-8")).hexdigest()
    return 60.0 + (int(digest[:6], 16) % 850) / 10.0


def checkpoint(job_id: str, payload: dict[str, Any]) -> None:
    DB["pipeline_checkpoints"].update_one(
        {"job_id": job_id},
        {"$set": payload},
        upsert=True,
    )


def publish_records(job_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    producer = get_producer()
    published = 0
    failed = 0
    started = time.time()
    for record in records:
        try:
            producer.send(KAFKA_PIPELINE_TOPIC, record)
            published += 1
            if published % 5000 == 0:
                producer.flush(timeout=5)
        except Exception:
            failed += 1
            producer.send(
                KAFKA_PIPELINE_DLQ_TOPIC,
                {
                    "record": record,
                    "error": "publish_error",
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
    producer.flush(timeout=10)
    elapsed = max(time.time() - started, 0.001)
    result = {
        "job_id": job_id,
        "published": published,
        "failed": failed,
        "throughput_eps": round(published / elapsed, 2),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    checkpoint(job_id, result)
    return result


def parse_web_with_bs4(html: str, css_selector: str, max_points: int) -> list[float]:
    soup = BeautifulSoup(html, "html.parser")
    matches = soup.select(css_selector)
    points: list[float] = []
    for node in matches[:max_points]:
        text = node.get_text(strip=True)
        value = sum(ord(c) for c in text) % 120
        points.append(float(value))
    return points or [72.0]


def parse_web_with_selenium(url: str, css_selector: str, max_points: int) -> list[float]:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = None
    try:
        if SELENIUM_REMOTE_URL:
            driver = webdriver.Remote(command_executor=SELENIUM_REMOTE_URL, options=options)
        else:
            driver = webdriver.Chrome(options=options)
        driver.get(url)
        elements = driver.find_elements(By.CSS_SELECTOR, css_selector)
        points = []
        for element in elements[:max_points]:
            text = element.text.strip()
            value = sum(ord(c) for c in text) % 120
            points.append(float(value))
        return points or [70.0]
    finally:
        if driver:
            driver.quit()


@app.on_event("startup")
def startup() -> None:
    DB["pipeline_checkpoints"].create_index("job_id", unique=True)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "collector-service"}


@app.post("/pipeline/collect/api")
def collect_api(payload: APICollectRequest) -> dict[str, Any]:
    job_id = f"api-{payload.tenant_id}-{payload.study_id}-{int(time.time())}"
    total_points = payload.hours * 60 * payload.points_per_minute
    total_points = min(total_points, 2_000_000)
    records = []
    base_seed = f"{payload.source_name}:{payload.endpoint}"
    started = datetime.now(timezone.utc)
    for idx in range(total_points):
        records.append(
            {
                "record_id": f"{job_id}-{idx}",
                "tenant_id": payload.tenant_id,
                "study_id": payload.study_id,
                "source_name": payload.source_name,
                "source_type": "api",
                "metric": "heart_rate",
                "value": deterministic_value(base_seed, idx),
                "observed_at": started.isoformat(),
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    result = publish_records(job_id, records)
    result["hours_collected"] = payload.hours
    result["source_endpoint"] = payload.endpoint
    return result


@app.post("/pipeline/collect/web")
def collect_web(payload: WebCollectRequest) -> dict[str, Any]:
    job_id = f"web-{payload.tenant_id}-{payload.study_id}-{int(time.time())}"
    try:
        if payload.use_selenium:
            points = parse_web_with_selenium(payload.url, payload.css_selector, payload.max_points)
            parser = "selenium"
        else:
            response = httpx.get(payload.url, timeout=20.0)
            response.raise_for_status()
            points = parse_web_with_bs4(response.text, payload.css_selector, payload.max_points)
            parser = "beautifulsoup"
    except Exception as exc:
        checkpoint(
            job_id,
            {
                "job_id": job_id,
                "error": str(exc),
                "status": "failed",
                "failed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        raise HTTPException(status_code=502, detail=f"collect failed: {exc}")

    records = [
        {
            "record_id": f"{job_id}-{idx}",
            "tenant_id": payload.tenant_id,
            "study_id": payload.study_id,
            "source_name": payload.source_name,
            "source_type": "web",
            "parser": parser,
            "metric": "web_signal",
            "value": value,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        for idx, value in enumerate(points)
    ]
    result = publish_records(job_id, records)
    result["url"] = payload.url
    result["parser"] = parser
    return result


@app.post("/pipeline/collect/simulate-500h")
def collect_500_hours(
    tenant_id: str = "tenant-a",
    study_id: str = "study-a",
    source_name: str = "wearable-simulator",
) -> dict[str, Any]:
    payload = APICollectRequest(
        tenant_id=tenant_id,
        study_id=study_id,
        source_name=source_name,
        endpoint="sim://wearable",
        hours=500,
        points_per_minute=1,
    )
    return collect_api(payload)


@app.get("/pipeline/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = DB["pipeline_checkpoints"].find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job
