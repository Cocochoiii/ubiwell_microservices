#!/usr/bin/env python3
"""Run report-generation benchmark and persist output."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

BASE_URL = os.getenv("BENCH_API_BASE_URL", "http://localhost:8000")
TENANT_ID = os.getenv("BENCH_TENANT_ID", "tenant-a")
STUDY_ID = os.getenv("BENCH_STUDY_ID", "study-a")
USERNAME = os.getenv("BENCH_USERNAME", "researcher")
PASSWORD = os.getenv("BENCH_PASSWORD", "researcher123")
ROUNDS = int(os.getenv("BENCH_ROUNDS", "5"))


def req(method: str, path: str, headers: dict[str, str], payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(f"{BASE_URL}{path}", method=method, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    token_payload = req(
        "POST",
        "/auth/token",
        {"Content-Type": "application/json"},
        {"username": USERNAME, "password": PASSWORD},
    )
    token = token_payload["access_token"]
    headers = {"Authorization": f"Bearer {token}", "x-tenant-id": TENANT_ID}

    result = req("GET", f"/reports/studies/{STUDY_ID}/benchmark?rounds={ROUNDS}", headers)
    result["created_at_epoch"] = int(time.time())
    out_dir = Path("docs/perf/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"benchmark-{int(time.time())}.json"
    out_file.write_text(json.dumps(result, indent=2))
    print(f"Benchmark saved to {out_file}")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
