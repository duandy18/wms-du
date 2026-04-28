# tests/api/test_merchant_code_bindings_contract.py
from __future__ import annotations

from typing import Any, Dict, List

import pytest


def _assert_problem_shape(j: Dict[str, Any]) -> None:
    assert isinstance(j, dict)
    assert "message" in j
    assert "http_status" in j
    assert isinstance(j["http_status"], int)


def _assert_row_shape(row: Dict[str, Any]) -> None:
    assert set(row.keys()) == {
        "id",
        "platform",
        "store_code",
        "store",  # ✅ 新增
        "merchant_code",
        "fsku_id",
        "fsku",
        "reason",
        "created_at",
        "updated_at",  # ✅ current-only 新增
    }

    store = row["store"]
    assert set(store.keys()) == {"id", "store_name"}

    f = row["fsku"]
    assert set(f.keys()) == {"id", "code", "name", "status"}


async def _auth_headers(client) -> Dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    data = r.json()
    token = data.get("access_token")
    assert isinstance(token, str) and token
    return {"Authorization": f"Bearer {token}"}


async def _pick_any_item_id(client, headers: Dict[str, str]) -> int:
    r = await client.get("/items", params={"limit": 1}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list) and data
    return int(data[0]["id"])


async def _create_draft_fsku(
    client,
    headers: Dict[str, str],
    *,
    name: str = "FSKU-TEST",
    shape: str = "bundle",
) -> Dict[str, Any]:
    r = await client.post("/oms/fskus", json={"name": name, "shape": shape}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _replace_components(client, headers: Dict[str, str], fsku_id: int, components: List[dict]) -> Dict[str, Any]:
    r = await client.post(
        f"/oms/fskus/{fsku_id}/components",
        json={"components": components},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.anyio
async def test_list_contract_envelope_and_row_shape(client):
    resp = await client.get("/oms/merchant-code-bindings?current_only=true&limit=50&offset=0")
    assert resp.status_code == 200
    j = resp.json()

    assert j["ok"] is True
    data = j["data"]
    assert set(data.keys()) == {"items", "total", "limit", "offset"}
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)
    assert data["limit"] == 50
    assert data["offset"] == 0

    for row in data["items"]:
        _assert_row_shape(row)


@pytest.mark.anyio
async def test_list_filters_are_accepted(client):
    resp = await client.get(
        "/oms/merchant-code-bindings"
        "?platform=DEMO"
        "&store_code=1"
        "&merchant_code=ABC"
        "&current_only=true"
        "&fsku_id=1"
        "&fsku_code=FSKU"
        "&limit=10"
        "&offset=0"
    )

    if resp.status_code in (422, 500):
        _assert_problem_shape(resp.json())
        return

    assert resp.status_code == 200
    j = resp.json()
    assert j["ok"] is True
    assert "items" in j["data"]


@pytest.mark.anyio
async def test_bind_contract_success_or_problem(client):
    payload = {
        "platform": "DEMO",
        "store_code": "1",
        "merchant_code": "UT-MC-001",
        "fsku_id": 1,
        "reason": "UT contract",
    }
    resp = await client.post("/oms/merchant-code-bindings/bind", json=payload)

    if resp.status_code != 200:
        _assert_problem_shape(resp.json())
        return

    j = resp.json()
    assert j["ok"] is True
    _assert_row_shape(j["data"])


@pytest.mark.anyio
async def test_bind_returns_conflict_when_test_set_guard_blocks_non_test_store(client, monkeypatch):
    from app.oms.services import test_store_testset_guard_service as guard_module

    async def fake_load_component_item_ids(_session, *, fsku_id: int) -> list[int]:
        assert int(fsku_id) == 1
        return [1]

    class FakePlatformTestStoreService:
        def __init__(self, _session):
            pass

        async def is_test_store(self, *, platform: str, store_code: str, code: str = "DEFAULT") -> bool:
            assert platform == "DEMO"
            assert store_code == "NON-TEST-STORE"
            assert code == "DEFAULT"
            return False

    class FakeItemTestSetService:
        class NotFound(ValueError):
            pass

        class InTestSet(ValueError):
            pass

        def __init__(self, _session):
            pass

        async def assert_items_not_in_test_set(self, *, item_ids: list[int], set_code: str = "DEFAULT") -> None:
            assert item_ids == [1]
            assert set_code == "DEFAULT"
            raise self.InTestSet("items in test_set[DEFAULT]: [1]")

    monkeypatch.setattr(guard_module, "load_component_item_ids", fake_load_component_item_ids)
    monkeypatch.setattr(guard_module, "PlatformTestStoreService", FakePlatformTestStoreService)
    monkeypatch.setattr(guard_module, "ItemTestSetService", FakeItemTestSetService)

    headers = await _auth_headers(client)
    payload = {
        "platform": "DEMO",
        "store_code": "NON-TEST-STORE",
        "merchant_code": "UT-MC-GUARD-BLOCKED-001",
        "fsku_id": 1,
        "reason": "UT: guard should return conflict",
    }

    resp = await client.post("/oms/merchant-code-bindings/bind", json=payload, headers=headers)

    assert resp.status_code == 409, resp.text
    problem = resp.json()
    _assert_problem_shape(problem)
    assert problem["error_code"] == "conflict"
    assert "测试商品不能绑定到非测试店铺" in str(problem["message"])
    assert problem["context"]["platform"] == "DEMO"
    assert problem["context"]["store_code"] == "NON-TEST-STORE"
    assert problem["context"]["component_item_ids"] == [1]


@pytest.mark.anyio
async def test_retire_is_blocked_when_fsku_is_referenced_by_merchant_code_binding(client):
    """
    护栏契约：被 merchant_code_fsku_bindings 引用的 published FSKU，不允许 retire。
    预期：POST /fskus/{id}/retire -> 409 + Problem
    """
    headers = await _auth_headers(client)
    item_id = await _pick_any_item_id(client, headers)

    # 1) 新建草稿 FSKU -> 配组件 -> publish
    f = await _create_draft_fsku(client, headers, name="FSKU-RETIRE-BLOCKED-BY-BINDING")
    await _replace_components(
        client,
        headers,
        fsku_id=int(f["id"]),
        components=[{"item_id": item_id, "qty": 1, "role": "primary"}],
    )

    r_pub = await client.post(f"/oms/fskus/{f['id']}/publish", headers=headers)
    assert r_pub.status_code == 200, r_pub.text
    pub = r_pub.json()
    assert pub["status"] == "published"

    # 2) 写入一条 merchant_code -> 该 published FSKU 的绑定事实
    mc = "UT-MC-RETIRE-LOCK-001"
    payload = {
        "platform": "DEMO",
        "store_code": "1",
        "merchant_code": mc,
        "fsku_id": int(f["id"]),
        "reason": "UT: lock retire when referenced",
    }
    r_bind = await client.post("/oms/merchant-code-bindings/bind", json=payload, headers=headers)
    assert r_bind.status_code == 200, r_bind.text
    j = r_bind.json()
    assert j.get("ok") is True
    _assert_row_shape(j["data"])
    assert int(j["data"]["fsku_id"]) == int(f["id"])
    assert str(j["data"]["merchant_code"]) == mc

    # 3) retire 必须被阻断
    r_ret = await client.post(f"/oms/fskus/{f['id']}/retire", headers=headers)
    assert r_ret.status_code == 409, r_ret.text
    p = r_ret.json()
    _assert_problem_shape(p)

    msg = str(p.get("message") or "")
    assert ("绑定" in msg) or ("引用" in msg) or ("改绑" in msg) or ("解绑" in msg)
