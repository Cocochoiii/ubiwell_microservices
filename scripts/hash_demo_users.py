#!/usr/bin/env python3
"""Generate bcrypt-hashed AUTH_USERS_JSON payload for non-demo environments."""

from __future__ import annotations

import json

import bcrypt

seed = [
    {"username": "researcher", "password": "researcher123", "role": "researcher", "tenant_id": "tenant-a"},
    {"username": "clinician", "password": "clinician123", "role": "clinician", "tenant_id": "tenant-a"},
    {"username": "admin", "password": "admin123", "role": "admin", "tenant_id": "tenant-admin"},
]

hashed = []
for item in seed:
    hashed.append(
        {
            "username": item["username"],
            "password_hash": bcrypt.hashpw(item["password"].encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
            "role": item["role"],
            "tenant_id": item["tenant_id"],
        }
    )

print(json.dumps(hashed))
