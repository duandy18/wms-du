# tests/api/test_warehouse_shipping_providers_bulk_upsert_api.py
#
# 合同级 smoke tests for:
#   PUT /warehouses/{warehouse_id}/shipping-providers  (bulk upsert)
#
# 目标：
# - 覆盖 disable_missing 的关键语义：未出现的绑定会被置 inactive（不删除）
# - 不依赖手工 seed（尽量自动补齐 shipping_providers）
# - 不强行猜 warehouses 表字段（仓库没有就 skip）
#
# Phase 6 刚性契约：
# - shipping_providers.warehouse_id NOT NULL
# - 因此测试补种 shipping_providers 时必须写入 warehouse_id（使用当前选中的 warehouse）

from __future__ import annotations

import os
import time
from typing import Optional

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
    raise RuntimeError("Cannot import FastAPI app. Please confirm app entry (e.g. app.main:app).")


def _dsn() -> str:
    return os.environ.get("WMS_TEST_DATABASE_URL") or os.environ.get("WMS_DATABASE_URL") or ""


def _pick_one_id(engine, sql: str) -> Optional[int]:
    with engine.begin() as conn:
        row = conn.execute(text(sql)).mappings().first()
        if not row:
            return None
        return int(row["id"])


def _count_shipping_providers(engine) -> int:
    with engine.begin() as conn:
        row = conn.execute(text("SELECT COUNT(*) AS n FROM shipping_providers")).mappings().first()
        return int(row["n"]) if row else 0


def _pick_n_provider_ids(engine, n: int) -> Optional[list[int]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id FROM shipping_providers ORDER BY id ASC LIMIT :n"),
            {"n": n},
        ).mappings().all()
        if len(rows) < n:
            return None
        return [int(r["id"]) for r in rows]


def _try_seed_shipping_providers(engine, *, need_total: int, warehouse_id: int) -> None:
    """
    补种 shipping_providers，确保至少 need_total 条。
    Phase 6：必须写 warehouse_id（NOT NULL）。
    """
    suffix = int(time.time() * 1000) % 1_000_000
    insert_sql = text(
        """
        INSERT INTO shipping_providers (name, code, active, priority, warehouse_id)
        VALUES (:name, :code, :active, :priority, :warehouse_id)
        RETURNING id
        """
    )
    with engine.begin() as conn:
        n = int(conn.execute(text("SELECT COUNT(*) AS n FROM shipping_providers")).mappings().first()["n"])
        need = max(0, need_total - n)
        if need <= 0:
            return
        for i in range(need):
            conn.execute(
                insert_sql,
                {
                    "name": f"TEST-OUTLET-{suffix}-{i+1}",
                    "code": f"TST{suffix}{i+1}",
                    "active": True,
                    "priority": 0,
                    "warehouse_id": int(warehouse_id),
                },
            )


def test_bulk_upsert_contract_smoke():
    dsn = _dsn()
    if not dsn:
        pytest.skip("Missing WMS_TEST_DATABASE_URL/WMS_DATABASE_URL in env")

    engine = create_engine(dsn, future=True)

    wid = _pick_one_id(engine, "SELECT id FROM warehouses ORDER BY id ASC LIMIT 1")
    if not wid:
        pytest.skip("No warehouses in test DB. Seed at least 1 warehouse before running this test.")

    # 确保至少 3 个 shipping_providers（Phase 6：补种必须带 warehouse_id）
    if _count_shipping_providers(engine) < 3:
        try:
            _try_seed_shipping_providers(engine, need_total=3, warehouse_id=wid)
        except Exception as e:
            pytest.skip(f"Need at least 3 shipping_providers, and auto-seed failed: {e!r}")

    ids = _pick_n_provider_ids(engine, 3)
    if not ids or len(ids) < 3:
        pytest.skip("Need at least 3 shipping_providers in test DB (after auto-seed).")
    pid1, pid2, pid3 = ids[0], ids[1], ids[2]

    app = _import_app()
    client = TestClient(app)

    r = client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json().get("access_token")
    assert token, r.text
    headers = {"Authorization": f"Bearer {token}"}

    # Step A) 先 upsert 3 个为 active=true（disable_missing=false，避免先把别的关掉）
    payload_all3 = {
        "disable_missing": False,
        "items": [
            {"shipping_provider_id": pid1, "active": True, "priority": 100},
            {"shipping_provider_id": pid2, "active": True, "priority": 200},
            {"shipping_provider_id": pid3, "active": True, "priority": 300},
        ],
    }
    r0 = client.put(f"/warehouses/{wid}/shipping-providers", json=payload_all3, headers=headers)
    assert r0.status_code == 200, r0.text
    assert r0.json().get("ok") is True

    # Step B) 只提交 2 个，并 disable_missing=true -> 第 3 个应被置 inactive
    payload_2 = {
        "disable_missing": True,
        "items": [
            {"shipping_provider_id": pid1, "active": True, "priority": 100},
            {"shipping_provider_id": pid2, "active": True, "priority": 200},
        ],
    }
    r1 = client.put(f"/warehouses/{wid}/shipping-providers", json=payload_2, headers=headers)
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert body.get("ok") is True
    assert isinstance(body.get("data"), list)

    by_pid = {int(x["shipping_provider_id"]): x for x in body["data"]}
    assert pid3 in by_pid, "pid3 binding should exist (not deleted)"
    assert by_pid[pid3]["active"] is False, "pid3 should be set inactive when disable_missing=true"

    # Step C) 幂等：同 payload 再来一次仍 200
    r2 = client.put(f"/warehouses/{wid}/shipping-providers", json=payload_2, headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.json().get("ok") is True

    # warehouse not found -> 404
    r3 = client.put("/warehouses/999999/shipping-providers", json=payload_2, headers=headers)
    assert r3.status_code == 404

    # provider not found -> 404
    bad = {"disable_missing": False, "items": [{"shipping_provider_id": 999999, "active": True, "priority": 0}]}
    r4 = client.put(f"/warehouses/{wid}/shipping-providers", json=bad, headers=headers)
    assert r4.status_code == 404
