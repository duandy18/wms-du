# tests/api/test_devconsole_orders_api.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService


@pytest.mark.asyncio
async def test_dev_orders_view_roundtrip(client: AsyncClient, session: AsyncSession):
    """
    验证一条最小链路（不依赖 /orders 路由）：

      OrderService.ingest(...) 直接落一条订单
        → /dev/orders/{platform}/{shop_id}/{ext_order_no}
        → /debug/trace/{trace_id}

    这样测试只依赖服务层 + devconsole + trace，不受 FULL_ROUTES 开关影响。
    """

    platform = "PDD"
    shop_id = "1"
    ext_order_no = "ORD-3001"
    trace_id = "TRACE-DEV-ORD-3001"

    # 1) 用服务层直接落一条订单（绕过 /orders 路由）
    await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        occurred_at=datetime.now(timezone.utc),
        buyer_name="测试用户",
        buyer_phone="13800000000",
        order_amount=100,
        pay_amount=100,
        items=[
            {"item_id": 1, "qty": 2},
        ],
        address=None,
        extras=None,
        trace_id=trace_id,
    )
    await session.commit()

    # 2) 用 DevConsole Orders 查询
    resp2 = await client.get(f"/dev/orders/{platform}/{shop_id}/{ext_order_no}")
    assert resp2.status_code == 200
    view = resp2.json()

    order = view["order"]
    assert order["platform"] == platform
    assert order["shop_id"] == shop_id
    assert order["ext_order_no"] == ext_order_no

    # devconsole 返回的 trace_id 应该等于我们传入的 trace_id
    trace_id_from_api = view["trace_id"]
    assert "trace_id" in order
    assert trace_id_from_api == trace_id

    # 3) Trace 黑盒必须能查到这条 trace
    resp3 = await client.get(f"/debug/trace/{trace_id}")
    assert resp3.status_code == 200
    trace = resp3.json()
    assert trace["trace_id"] == trace_id
    events = trace["events"]
    assert isinstance(events, list)
    # 至少要有一条 audit 或 order 事件
    sources = {e["source"] for e in events}
    assert "audit" in sources or "order" in sources
