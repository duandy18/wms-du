# tests/api/test_shipping_quote_scheme_warehouses_api.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.api._helpers_shipping_quote import auth_headers, create_scheme_bundle, login, pick_warehouse_id, require_env


@pytest.fixture(scope="module")
def client() -> TestClient:
    require_env()
    return TestClient(app)


def test_pricing_scheme_warehouses_bind_and_unbind(client: TestClient) -> None:
    token = login(client)
    h = auth_headers(token)

    ids = create_scheme_bundle(client, token)
    scheme_id = ids["scheme_id"]
    wid = pick_warehouse_id(client, token)

    # 初始读
    r0 = client.get(f"/pricing-schemes/{scheme_id}/warehouses", headers=h)
    assert r0.status_code == 200, r0.text

    # 绑定
    rb = client.put(
        f"/pricing-schemes/{scheme_id}/warehouses",
        headers=h,
        json={"warehouse_ids": [wid], "active": True},
    )
    assert rb.status_code == 200, rb.text
    data = rb.json()["data"]
    assert any(int(x["warehouse_id"]) == int(wid) and bool(x["active"]) is True for x in data)

    # 再读确认
    r1 = client.get(f"/pricing-schemes/{scheme_id}/warehouses", headers=h)
    assert r1.status_code == 200, r1.text
    data1 = r1.json()["data"] or []
    assert any(int(x["warehouse_id"]) == int(wid) and bool(x["active"]) is True for x in data1)

    # 解绑（全量置空）
    ru = client.put(
        f"/pricing-schemes/{scheme_id}/warehouses",
        headers=h,
        json={"warehouse_ids": [], "active": True},
    )
    assert ru.status_code == 200, ru.text
    assert ru.json()["data"] == []
