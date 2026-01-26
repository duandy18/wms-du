from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


def _import_app():
    for mod in ("app.main", "app.api.main", "app.app"):
        try:
            m = __import__(mod, fromlist=["app"])
            return getattr(m, "app")
        except Exception:
            continue
    raise RuntimeError("Cannot import FastAPI app. Please confirm app entry.")


def _dsn() -> str:
    return os.environ.get("WMS_TEST_DATABASE_URL") or os.environ.get("WMS_DATABASE_URL") or ""


def _pick_warehouse_id(engine) -> int | None:
    with engine.begin() as conn:
        r = conn.execute(text("SELECT id FROM warehouses ORDER BY id ASC LIMIT 1")).mappings().first()
        return int(r["id"]) if r else None


def test_shipping_provider_create_requires_warehouse_id():
    dsn = _dsn()
    if not dsn:
        pytest.skip("missing dsn")
    engine = create_engine(dsn, future=True)
    wid = _pick_warehouse_id(engine)
    if not wid:
        pytest.skip("need at least 1 warehouse")

    app = _import_app()
    c = TestClient(app)

    r = c.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json().get("access_token")
    assert token
    headers = {"Authorization": f"Bearer {token}"}

    suffix = int(time.time() * 1000) % 1_000_000

    r1 = c.post(
        "/shipping-providers",
        json={"name": f"TEST-OUTLET-{suffix}", "code": f"TST{suffix}", "active": True, "priority": 100},
        headers=headers,
    )
    assert r1.status_code == 422, r1.text

    r2 = c.post(
        "/shipping-providers",
        json={
            "name": f"TEST-OUTLET-{suffix}",
            "code": f"TST{suffix}",
            "active": True,
            "priority": 100,
            "warehouse_id": wid,
        },
        headers=headers,
    )
    assert r2.status_code == 201, r2.text
    body = r2.json()
    assert body.get("ok") is True
    assert int(body["data"]["warehouse_id"]) == wid

    r3 = c.get("/shipping-providers", headers=headers)
    assert r3.status_code == 200
    data = r3.json()["data"]
    assert any(int(x.get("warehouse_id")) == wid for x in data)
