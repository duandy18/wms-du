# tests/api/test_orders_create_contract.py
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_platform_orders_ingest_minimal_contract(client: TestClient) -> None:
    """
    验证当前订单接入真身 /oms/platform-orders/ingest 的最小契约：

    - 支持 platform / shop_id / ext_order_no + 顶层地址字段 + lines 接入；
    - 返回 JSON 中至少包含：
        status / id / ref / resolved / unresolved / facts_written；
    - 不强制必须成功建单：
        * 允许进入 UNRESOLVED / FULFILLMENT_BLOCKED / OK / IDEMPOTENT 等现态结果；
        * 重点是“进入当前主线并返回结构化结果”，而不是旧 /orders 时代的最小建单语义。
    - ref 仍采用 "ORD:{platform}:{shop_id}:{ext_order_no}" 格式。
    """
    payload = {
        "platform": "PDD",
        "shop_id": "TEST_SHOP_ORD",
        "ext_order_no": "TEST_ORDER_001",
        "buyer_name": "测试买家",
        "buyer_phone": "13800000000",
        "receiver_name": "X",
        "receiver_phone": "000",
        "province": "UT-PROV",
        "lines": [
            {
                "title": "测试商品 A",
                "qty": 2,
            },
            {
                "title": "测试商品 B",
                "qty": 1,
            },
        ],
    }

    resp = client.post("/oms/platform-orders/ingest", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "status" in data
    assert "id" in data
    assert "ref" in data
    assert "resolved" in data
    assert "unresolved" in data
    assert "facts_written" in data

    assert isinstance(data["status"], str) and data["status"]
    assert isinstance(data["id"], int) or data["id"] is None
    assert isinstance(data["resolved"], list)
    assert isinstance(data["unresolved"], list)
    assert isinstance(data["facts_written"], int)

    expected_ref = f"ORD:{payload['platform']}:{payload['shop_id']}:{payload['ext_order_no']}"
    assert data["ref"] == expected_ref


def test_platform_orders_ingest_with_no_lines_still_returns_structured_result(
    client: TestClient,
) -> None:
    """
    验证空行输入时，当前接入主线至少返回结构化结果，不抛 5xx。
    """
    payload = {
        "platform": "PDD",
        "shop_id": "TEST_SHOP_ORD",
        "ext_order_no": "TEST_ORDER_NO_LINES",
        "receiver_name": "X",
        "receiver_phone": "000",
        "province": "UT-PROV",
        "lines": [],
    }

    resp = client.post("/oms/platform-orders/ingest", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "status" in data
    assert "id" in data
    assert "ref" in data
    assert "resolved" in data
    assert "unresolved" in data
    assert "facts_written" in data

    assert isinstance(data["status"], str) and data["status"]
    assert isinstance(data["resolved"], list)
    assert isinstance(data["unresolved"], list)
    assert isinstance(data["facts_written"], int)
    assert data["ref"].startswith("ORD:PDD:TEST_SHOP_ORD:")
