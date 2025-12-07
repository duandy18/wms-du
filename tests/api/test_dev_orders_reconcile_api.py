# tests/api/test_dev_orders_reconcile_api.py
from __future__ import annotations

from typing import Any, Dict

import pytest


def _make_order_payload(platform: str, shop_id: str, ext_no: str) -> Dict[str, Any]:
    """
    构造一个最小化的 /orders 创建载荷：
    - 1 个 item_id=1，qty=1
    - 金额字段随便给个值，关键在于订单成功落库
    """
    return {
        "platform": platform,
        "shop_id": shop_id,
        "ext_order_no": ext_no,
        "buyer_name": "对账测试用户",
        "buyer_phone": "13800000000",
        "order_amount": 10.0,
        "pay_amount": 10.0,
        "lines": [
            {
                "item_id": 1,
                "qty": 1,
            },
        ],
    }


@pytest.mark.asyncio
async def test_dev_orders_reconcile_by_id_not_found(client) -> None:
    """
    当订单不存在时，/dev/orders/by-id/{order_id}/reconcile 应返回 404。
    这个测试主要验证路由存在且行为合理。
    """
    resp = await client.get("/dev/orders/by-id/999999/reconcile")
    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert "detail" in body


@pytest.mark.asyncio
async def test_dev_orders_reconcile_by_id_roundtrip(client) -> None:
    """
    一条完整链路：

      1. 通过 /orders 创建一条新订单；
      2. 从返回体中拿到 order_id；
      3. 调 /dev/orders/by-id/{order_id}/reconcile；
      4. 验证返回结构中有 order_id / issues / lines 等字段。

    这里只验证 API 契约和基本结构，不强求具体业务数值。
    """

    platform = "PDD"
    shop_id = "RECON_TEST_SHOP"
    ext_no = "RECON-TEST-001"

    # 1) 创建订单
    payload = _make_order_payload(platform, shop_id, ext_no)
    resp = await client.post("/orders", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("status") in ("OK", "IDEMPOTENT")
    order_id = data.get("id")
    assert isinstance(order_id, int) and order_id > 0

    # 2) 调用 /dev/orders/by-id/{order_id}/reconcile
    resp2 = await client.get(f"/dev/orders/by-id/{order_id}/reconcile")
    assert resp2.status_code == 200, resp2.text

    body = resp2.json()
    # 基本结构检查
    assert body.get("order_id") == order_id
    assert body.get("platform") == platform.upper()
    assert body.get("shop_id") == shop_id
    assert body.get("ext_order_no") == ext_no
    assert "issues" in body
    assert isinstance(body["issues"], list)
    assert "lines" in body
    assert isinstance(body["lines"], list)
    # 行的基本字段检查（至少有 item_id / qty_*）
    if body["lines"]:
        line0 = body["lines"][0]
        assert "item_id" in line0
        assert "qty_ordered" in line0
        assert "qty_shipped" in line0
        assert "qty_returned" in line0
        assert "remaining_refundable" in line0
