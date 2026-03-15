from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from conftest import load_module


def test_role_based_widget_access():
    mod = load_module("realtime_service_main_roles", "services/realtime-service/app/main.py")
    assert mod.role_allowed("admin", "critical_alerts_only") is True
    assert mod.role_allowed("researcher", "critical_alerts_only") is False
    assert mod.role_allowed("clinician", "critical_alerts_only") is True


def test_websocket_rejects_tenant_mismatch():
    mod = load_module("realtime_service_main_ws", "services/realtime-service/app/main.py")
    token = jwt.encode(
        {"sub": "researcher", "role": "researcher", "tenant_id": "tenant-a"},
        mod.JWT_SECRET,
        algorithm=mod.JWT_ALGORITHM,
    )

    client = TestClient(mod.app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/studies/study-a?tenant_id=tenant-b&token={token}"):
            pass
