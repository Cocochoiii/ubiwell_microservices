#!/usr/bin/env python3
"""Seed demo tenant data through API Gateway endpoints."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

BASE_URL = os.getenv("DEMO_BASE_URL", "http://localhost:8000")
TENANT_ID = os.getenv("DEMO_TENANT_ID", "tenant-a")
USERNAME = os.getenv("DEMO_USERNAME", "researcher")
PASSWORD = os.getenv("DEMO_PASSWORD", "researcher123")
EVENT_COUNT = int(os.getenv("DEMO_EVENT_COUNT", "60"))


def request_json(method: str, path: str, body: dict | None = None, headers: dict | None = None) -> dict:
    data = None
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = resp.read().decode("utf-8")
        return json.loads(payload) if payload else {}


def get_token() -> str:
    payload = {"username": USERNAME, "password": PASSWORD}
    resp = request_json("POST", "/auth/token", body=payload)
    token = resp.get("access_token")
    if not token:
        raise RuntimeError("failed to get access token")
    return token


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "x-tenant-id": TENANT_ID}


def main() -> int:
    try:
        token = get_token()
        headers = auth_headers(token)

        participants = [
            {"participant_id": "p-1001", "study_id": "study-a", "status": "active"},
            {"participant_id": "p-1002", "study_id": "study-a", "status": "active"},
            {"participant_id": "p-1003", "study_id": "study-a", "status": "paused"},
            {"participant_id": "p-2001", "study_id": "study-b", "status": "active"},
        ]
        for p in participants:
            request_json("POST", "/participants", body=p, headers=headers)

        responses = [
            {"study_id": "study-a", "participant_id": "p-1001", "survey_id": "baseline", "answers": {"q1": 5, "q2": 4}},
            {"study_id": "study-a", "participant_id": "p-1002", "survey_id": "baseline", "answers": {"q1": 3, "q2": 2}},
            {"study_id": "study-b", "participant_id": "p-2001", "survey_id": "followup", "answers": {"q1": 4, "q2": 5}},
        ]
        for r in responses:
            request_json("POST", "/survey/responses", body=r, headers=headers)

        for i in range(EVENT_COUNT):
            event = {
                "event_id": f"evt-seed-{i}",
                "study_id": "study-a",
                "participant_id": "p-1001" if i % 2 == 0 else "p-1002",
                "event_type": "heart_rate" if i % 3 else "spo2",
                "value": 78.0 + (i % 12) if i % 3 else 92.0 - (i % 5),
                "source_device": "fitband-v2",
            }
            request_json("POST", "/events", body=event, headers=headers)

        report = request_json("GET", "/analytics/studies/study-a/report", headers=headers)
        print(json.dumps({"seeded": True, "tenant_id": TENANT_ID, "report_preview": report}, indent=2))
        return 0
    except urllib.error.HTTPError as exc:
        print(f"HTTP error during seed: {exc.code} {exc.reason}")
        if exc.fp:
            print(exc.fp.read().decode("utf-8"))
        return 1
    except Exception as exc:
        print(f"Seed failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
