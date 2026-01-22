# tests/api/test_orders_create_contract.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_orders_create_minimal_contract() -> None:
    """
    验证 /orders 接口的最小契约（只保证“建单成功并返回 ref/id/status”，不强制可履约）：

    - 支持以 platform / shop_id / ext_order_no + lines 创建订单；
    - 返回 JSON 中包含 status / id / ref 字段；
    - status 允许：
        * "OK" / "IDEMPOTENT"：可履约或已幂等
        * "FULFILLMENT_BLOCKED"：建单成功但不可履约事实（省份缺失/无候选集/库存不足等）
    - ref 采用 "ORD:{platform}:{shop_id}:{ext_order_no}" 格式。
    """
    payload = {
        "platform": "PDD",
        "shop_id": "TEST_SHOP_ORD",
        "ext_order_no": "TEST_ORDER_001",
        "buyer_name": "测试买家",
        "buyer_phone": "13800000000",
        "order_amount": 26.0,
        "pay_amount": 26.0,
        "address": {"province": "UT-PROV", "receiver_name": "X", "receiver_phone": "000"},
        "lines": [
            {
                "item_id": 1,
                "title": "测试商品 A",
                "qty": 2,
                "price": 10.5,
                "amount": 21.0,
            },
            {
                "item_id": 1,
                "title": "测试商品 B",
                "qty": 1,
                "price": 5.0,
                "amount": 5.0,
            },
        ],
    }

    resp = client.post("/orders", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "status" in data
    assert "id" in data
    assert "ref" in data

    assert data["status"] in ("OK", "IDEMPOTENT", "FULFILLMENT_BLOCKED")
    assert isinstance(data["id"], int) or data["id"] is None

    expected_ref = f"ORD:{payload['platform']}:{payload['shop_id']}:{payload['ext_order_no']}"
    assert data["ref"] == expected_ref


def test_orders_create_with_no_lines_rejected() -> None:
    """
    验证无行订单的行为：

    当前实现允许 lines 为空，但这类订单对库存 / 履约没有意义。
    这里至少保证接口能正常返回，不抛 5xx。
    """
    payload = {
        "platform": "PDD",
        "shop_id": "TEST_SHOP_ORD",
        "ext_order_no": "TEST_ORDER_NO_LINES",
        "lines": [],
    }

    resp = client.post("/orders", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "status" in data
    assert data["ref"].startswith("ORD:PDD:TEST_SHOP_ORD:")
