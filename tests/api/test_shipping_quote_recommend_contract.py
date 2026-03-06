# tests/api/test_shipping_quote_recommend_contract.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.api._helpers_shipping_quote import (
    auth_headers,
    bind_provider_to_warehouse,
    clear_warehouse_bindings,
    create_scheme_bundle_for_provider,
    ensure_second_provider,
    login,
    pick_warehouse_id,
    require_env,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    require_env()
    return TestClient(app)


def test_shipping_quote_recommend_respects_warehouse_bound_candidates_phase3(client: TestClient) -> None:
    """
    Phase 3 / Route A 严格合同：
    - warehouse_id 下候选 provider 必须来自仓库绑定（事实）
    - 候选 scheme 必须属于该仓（scheme.warehouse_id = warehouse_id）
    """
    token = login(client)
    h = auth_headers(token)

    wid = pick_warehouse_id(client, token)
    clear_warehouse_bindings(client, token, wid)

    pr = client.get("/shipping-providers", headers=h)
    assert pr.status_code == 200, pr.text
    pdata = pr.json()["data"]
    assert pdata, "no shipping providers"
    provider_a = int(pdata[0]["id"])

    bind_provider_to_warehouse(client, token, wid, provider_a)
    ids_a = create_scheme_bundle_for_provider(client, token, provider_a, name_suffix="A")

    # 先确认 scheme 对该 dest 可算，避免“calc 全失败导致 recommend 空”的假阴性
    cr = client.post(
        "/shipping-quote/calc",
        headers=h,
        json={
            "warehouse_id": wid,
            "scheme_id": ids_a["scheme_id"],
            "dest": {
                "province": "河北省",
                "city": "廊坊市",
                "district": "固安县",
                "province_code": "130000",
                "city_code": "131000",
            },
            "real_weight_kg": 1.0,
            "flags": [],
        },
    )
    assert cr.status_code == 200, cr.text
    assert cr.json()["quote_status"] == "OK"

    rr = client.post(
        "/shipping-quote/recommend",
        headers=h,
        json={
            "warehouse_id": wid,
            "provider_ids": [],
            "dest": {
                "province": "河北省",
                "city": "廊坊市",
                "district": "固安县",
                "province_code": "130000",
                "city_code": "131000",
            },
            "real_weight_kg": 1.0,
            "flags": [],
            "max_results": 10,
        },
    )
    assert rr.status_code == 200, rr.text
    body = rr.json()
    assert body["ok"] is True
    quotes = body["quotes"]
    assert quotes, "expected non-empty quotes when warehouse has enabled provider and warehouse-scoped scheme"
    assert all(int(q["provider_id"]) == provider_a for q in quotes)
    assert body["recommended_scheme_id"] is not None
    assert any(int(q["scheme_id"]) == ids_a["scheme_id"] for q in quotes)


def test_shipping_quote_recommend_provider_ids_intersect_warehouse_phase3(client: TestClient) -> None:
    """
    Phase 3 / Route A 严格合同：
    - warehouse_id 存在时，provider_ids 只能过滤交集，不允许 override 仓库边界
    - provider B 未绑定到仓库 -> 即使 provider_ids=[B] 也必须空

    说明：
    - Route A 下 create_scheme_bundle_for_provider() 会自动把 provider 绑定到 pick_warehouse_id() 返回的仓。
    - 因此这里不能为 provider_b 调用该 helper，否则测试会自己把 provider_b 绑定到当前仓，前提失真。
    """
    token = login(client)
    h = auth_headers(token)

    wid = pick_warehouse_id(client, token)
    clear_warehouse_bindings(client, token, wid)

    pr = client.get("/shipping-providers", headers=h)
    assert pr.status_code == 200, pr.text
    pdata = pr.json()["data"]
    assert pdata, "no shipping providers"
    provider_a = int(pdata[0]["id"])

    bind_provider_to_warehouse(client, token, wid, provider_a)
    ids_a2 = create_scheme_bundle_for_provider(client, token, provider_a, name_suffix="A2")
    assert ids_a2["scheme_id"] > 0

    provider_b = ensure_second_provider(client, token)
    # 关键：不要给 provider_b 创建 bundle。
    # 否则 create_scheme_bundle_for_provider() 会自动把 provider_b 绑定到当前仓 wid，
    # 破坏“provider_b 未绑定当前仓”的测试前提。

    rr = client.post(
        "/shipping-quote/recommend",
        headers=h,
        json={
            "warehouse_id": wid,
            "provider_ids": [provider_b],
            "dest": {
                "province": "河北省",
                "city": "廊坊市",
                "district": "固安县",
                "province_code": "130000",
                "city_code": "131000",
            },
            "real_weight_kg": 1.0,
            "flags": [],
            "max_results": 10,
        },
    )
    assert rr.status_code == 200, rr.text
    body = rr.json()
    assert body["ok"] is True
    assert body["quotes"] == []
    assert body["recommended_scheme_id"] is None
