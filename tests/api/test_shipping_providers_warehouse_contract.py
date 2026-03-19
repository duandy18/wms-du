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


def test_shipping_provider_create_then_bind_to_warehouse_contract():
    """
    最新合同（Phase 6+）：
    - /shipping-providers 创建网点实体不再要求 warehouse_id（M:N 绑定关系在 warehouse_shipping_providers）
    - 绑定关系通过 /tms/pricing/warehouses/{warehouse_id}/bindings 建立
    """
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
    name = f"TEST-OUTLET-{suffix}"
    code = f"TST{suffix}"

    # 1) 创建网点实体（不需要 warehouse_id）
    r1 = c.post(
        "/shipping-providers",
        json={"name": name, "code": code, "active": True, "priority": 100},
        headers=headers,
    )
    assert r1.status_code == 201, r1.text
    body1 = r1.json()
    assert body1.get("ok") is True
    provider_id = int(body1["data"]["id"])
    assert body1["data"]["name"] == name
    assert body1["data"]["code"] == code

    # 2) 绑定到仓库（M:N）
    r2 = c.post(
        f"/tms/pricing/warehouses/{wid}/bindings",
        json={"shipping_provider_id": provider_id, "active": True, "priority": 100},
        headers=headers,
    )
    assert r2.status_code == 201, r2.text
    body2 = r2.json()
    assert body2.get("ok") is True
    assert int(body2["data"]["warehouse_id"]) == wid
    assert int(body2["data"]["shipping_provider_id"]) == provider_id

    # 3) 从仓库绑定列表中可见
    r3 = c.get(f"/tms/pricing/warehouses/{wid}/bindings", headers=headers)
    assert r3.status_code == 200, r3.text
    rows = r3.json()["data"]
    assert any(int(x["shipping_provider_id"]) == provider_id for x in rows)

    # 4) 全局网点列表可见（不要求 warehouse_id 字段存在）
    r4 = c.get("/shipping-providers", headers=headers)
    assert r4.status_code == 200, r4.text
    data = r4.json()["data"]
    assert any(int(x["id"]) == provider_id for x in data)
