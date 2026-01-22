# tests/api/test_shipping_quote_scheme_warehouses_api.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.api._helpers_shipping_quote import (
    auth_headers,
    create_scheme_bundle,
    login,
    pick_warehouse_id,
    require_env,
    bind_scheme_to_warehouse,
    unbind_scheme_from_warehouse,
)


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

    # 绑定（新合同：bind）
    bind_scheme_to_warehouse(client, token, scheme_id, wid)

    # 再读确认
    r1 = client.get(f"/pricing-schemes/{scheme_id}/warehouses", headers=h)
    assert r1.status_code == 200, r1.text
    data1 = r1.json()["data"] or []
    assert any(int(x["warehouse_id"]) == int(wid) and bool(x["active"]) is True for x in data1)

    # 解绑（新合同：delete）
    unbind_scheme_from_warehouse(client, token, scheme_id, wid)

    r2 = client.get(f"/pricing-schemes/{scheme_id}/warehouses", headers=h)
    assert r2.status_code == 200, r2.text
    assert r2.json()["data"] == []
