from __future__ import annotations

import json

import pytest

from conftest import load_module


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.store[key] = value

    async def delete(self, *keys: str):
        for key in keys:
            self.store.pop(key, None)

    async def scan_iter(self, match: str):
        prefix = match.replace("*", "")
        for key in list(self.store.keys()):
            if key.startswith(prefix):
                yield key


class FakeDeleteCollection:
    def __init__(self) -> None:
        self.deleted: list[dict] = []

    def delete_many(self, query: dict):
        self.deleted.append(query)


class FakeDb:
    def __init__(self) -> None:
        self.collection = FakeDeleteCollection()

    def __getitem__(self, item: str):
        if item != "report_aggregates":
            raise KeyError(item)
        return self.collection


@pytest.mark.asyncio
async def test_report_cache_hit_and_miss():
    mod = load_module("report_service_main_cache", "services/report-service/app/main.py")
    mod.redis_client = FakeRedis()
    mod.L1_CACHE.clear()

    calls = {"count": 0}

    def fake_compute(tenant_id: str, study_id: str):
        calls["count"] += 1
        return {
            "tenant_id": tenant_id,
            "study_id": study_id,
            "top_participants": [{"participant_id": "p-1", "events": 10}],
        }

    mod.compute_report_optimized = fake_compute

    first = await mod.get_or_build_report("tenant-a", "study-a", 1, 10, None, force_refresh=False)
    second = await mod.get_or_build_report("tenant-a", "study-a", 1, 10, None, force_refresh=False)

    assert first["pagination"]["total"] == 1
    assert second["cache_layer"] == "l1_memory"
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_invalidate_report_cache_removes_layers():
    mod = load_module("report_service_main_invalidate", "services/report-service/app/main.py")
    fake_redis = FakeRedis()
    await fake_redis.set("report:tenant-a:study-a:1:25:all", json.dumps({"ok": True}))
    mod.redis_client = fake_redis
    mod.db = FakeDb()
    mod.L1_CACHE = {"report:tenant-a:study-a:1:25:all": (9999999999, {"ok": True})}

    result = await mod.invalidate_report_cache("study-a", x_tenant_id="tenant-a")

    assert result["redis_keys"] == 1
    assert result["l1_keys"] == 1
    assert mod.L1_CACHE == {}
