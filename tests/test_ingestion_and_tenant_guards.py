from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from conftest import load_module


ROOT = Path(__file__).resolve().parents[1]
PROTO_GEN_PATH = ROOT / "shared" / "gen"
if str(PROTO_GEN_PATH) not in sys.path:
    sys.path.insert(0, str(PROTO_GEN_PATH))


def _event_payload(mod, *, tenant_id: str | None = None, event_id: str = "evt-1"):
    return mod.EventIngest(
        tenant_id=tenant_id,
        event_id=event_id,
        study_id="study-a",
        participant_id="p-1",
        event_type="heart_rate",
        value=80.0,
    )


def test_ingestion_rejects_tenant_mismatch() -> None:
    mod = load_module("ingestion_service_main_tenant_mismatch", "services/ingestion-service/app/main.py")
    payload = _event_payload(mod, tenant_id="tenant-a")

    with pytest.raises(HTTPException) as exc:
        mod.ingest_event(payload, x_tenant_id="tenant-b")

    assert exc.value.status_code == 403
    assert "tenant mismatch" in str(exc.value.detail)


def test_ingestion_buffers_and_returns_503_when_publish_fails() -> None:
    mod = load_module("ingestion_service_main_buffer_fail", "services/ingestion-service/app/main.py")
    mod.INGESTION_BUFFER.clear()
    mod.BUFFERED_EVENT_IDS.clear()
    mod.SEEN_EVENT_IDS.clear()
    mod.publish_event = lambda event: (_ for _ in ()).throw(RuntimeError("kafka unavailable"))

    payload = _event_payload(mod, event_id="evt-buffer-1")
    with pytest.raises(HTTPException) as exc:
        mod.ingest_event(payload, x_tenant_id="tenant-a")

    assert exc.value.status_code == 503
    assert len(mod.INGESTION_BUFFER) == 1
    assert "evt-buffer-1" in mod.BUFFERED_EVENT_IDS
    assert "evt-buffer-1" not in mod.SEEN_EVENT_IDS


def test_ingestion_flush_buffer_republishes_buffered_event() -> None:
    mod = load_module("ingestion_service_main_buffer_flush", "services/ingestion-service/app/main.py")
    mod.INGESTION_BUFFER.clear()
    mod.BUFFERED_EVENT_IDS.clear()
    mod.SEEN_EVENT_IDS.clear()
    published: list[dict] = []
    mod.publish_event = lambda event: published.append(event)

    buffered_event = {
        "tenant_id": "tenant-a",
        "event_id": "evt-flush-1",
        "study_id": "study-a",
        "participant_id": "p-1",
        "event_type": "heart_rate",
        "value": 90.0,
    }
    assert mod.buffer_event(buffered_event, "evt-flush-1") is False

    flushed = mod.flush_buffer_once()

    assert flushed == 1
    assert len(published) == 1
    assert mod.INGESTION_BUFFER == []
    assert "evt-flush-1" not in mod.BUFFERED_EVENT_IDS
    assert "evt-flush-1" in mod.SEEN_EVENT_IDS


@pytest.mark.parametrize(
    ("module_name", "relative_path", "payload_builder"),
    [
        (
            "participant_service_main_tenant_guard",
            "services/participant-service/app/main.py",
            lambda mod: mod.ParticipantCreate(
                tenant_id="tenant-a",
                participant_id="p-1",
                study_id="study-a",
                status="active",
            ),
        ),
        (
            "survey_service_main_tenant_guard",
            "services/survey-service/app/main.py",
            lambda mod: mod.SurveyResponseCreate(
                tenant_id="tenant-a",
                study_id="study-a",
                participant_id="p-1",
                survey_id="baseline",
                answers={"q1": "yes"},
            ),
        ),
    ],
)
def test_internal_services_reject_tenant_mismatch(module_name: str, relative_path: str, payload_builder) -> None:
    mod = load_module(module_name, relative_path)
    payload = payload_builder(mod)

    target_fn = mod.create_participant if "participant-service" in relative_path else mod.create_response
    with pytest.raises(HTTPException) as exc:
        target_fn(payload, x_tenant_id="tenant-b")

    assert exc.value.status_code == 403
    assert "tenant mismatch" in str(exc.value.detail)


def test_ingestion_http_rejects_tenant_mismatch() -> None:
    mod = load_module("ingestion_service_main_http_tenant_mismatch", "services/ingestion-service/app/main.py")
    client = TestClient(mod.app)

    response = client.post(
        "/events",
        headers={"x-tenant-id": "tenant-b"},
        json={
            "tenant_id": "tenant-a",
            "event_id": "evt-http-1",
            "study_id": "study-a",
            "participant_id": "p-1",
            "event_type": "heart_rate",
            "value": 80.0,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "tenant mismatch"


def test_ingestion_http_returns_503_when_publish_fails() -> None:
    mod = load_module("ingestion_service_main_http_publish_fail", "services/ingestion-service/app/main.py")
    mod.INGESTION_BUFFER.clear()
    mod.BUFFERED_EVENT_IDS.clear()
    mod.SEEN_EVENT_IDS.clear()
    mod.publish_event = lambda event: (_ for _ in ()).throw(RuntimeError("kafka unavailable"))
    client = TestClient(mod.app)

    response = client.post(
        "/events",
        headers={"x-tenant-id": "tenant-a"},
        json={
            "event_id": "evt-http-2",
            "study_id": "study-a",
            "participant_id": "p-1",
            "event_type": "heart_rate",
            "value": 81.0,
        },
    )

    assert response.status_code == 503
    assert "buffered locally" in response.json()["detail"]
    assert len(mod.INGESTION_BUFFER) == 1


def test_participant_http_rejects_tenant_mismatch() -> None:
    mod = load_module("participant_service_main_http_tenant_guard", "services/participant-service/app/main.py")
    client = TestClient(mod.app)

    response = client.post(
        "/participants",
        headers={"x-tenant-id": "tenant-b"},
        json={
            "tenant_id": "tenant-a",
            "participant_id": "p-http-1",
            "study_id": "study-a",
            "status": "active",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "tenant mismatch"


def test_survey_http_rejects_tenant_mismatch() -> None:
    mod = load_module("survey_service_main_http_tenant_guard", "services/survey-service/app/main.py")
    client = TestClient(mod.app)

    response = client.post(
        "/responses",
        headers={"x-tenant-id": "tenant-b"},
        json={
            "tenant_id": "tenant-a",
            "study_id": "study-a",
            "participant_id": "p-http-1",
            "survey_id": "baseline",
            "answers": {"q1": "yes"},
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "tenant mismatch"
