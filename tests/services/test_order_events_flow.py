# tests/services/test_order_events_flow.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService

UTC = timezone.utc


@pytest.mark.asyncio
async def test_order_created_and_reserved_events(session: AsyncSession) -> None:
    """
    验证 OrderEventBus 事件流：

      - OrderService.ingest → 写 ORDER_CREATED 事件；
      - OrderService.reserve → 写 ORDER_RESERVED 事件；
      - 两条事件共享同一个 trace_id；
      - category=ORDER，meta.event = ORDER_*，ref = ORD:{PLAT}:{shop_id}:{ext_no}。
    """
    platform = "PDD"
    shop_id = "EVT_TEST_SHOP"
    ext_order_no = "EVT-TEST-ORDER-001"
    trace_id = "TRACE-EVT-ORDER-001"

    plat = platform.upper()
    ref = f"ORD:{plat}:{shop_id}:{ext_order_no}"

    # 先清一下可能的历史审计事件 / 预占记录（仅限本 ref）
    await session.execute(
        text("DELETE FROM audit_events WHERE category = 'ORDER' AND ref = :ref"),
        {"ref": ref},
    )
    await session.execute(
        text("DELETE FROM reservations WHERE platform = :p AND shop_id = :s AND ref = :ref"),
        {"p": plat, "s": shop_id, "ref": ref},
    )

    # 1) ingest 创建订单
    result = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        occurred_at=datetime.now(UTC),
        buyer_name="事件测试用户",
        buyer_phone="13800000000",
        order_amount=10,
        pay_amount=10,
        items=[{"item_id": 1, "qty": 1}],
        address=None,
        extras=None,
        trace_id=trace_id,
    )
    assert result["status"] == "OK"
    assert result["ref"] == ref
    order_id = int(result["id"])

    # 2) 为测试手动指定订单履约仓（避免依赖路由 / 渠道库存环境）
    await session.execute(
        text(
            """
            UPDATE orders
               SET warehouse_id = 1
             WHERE id = :oid
            """
        ),
        {"oid": order_id},
    )

    # 3) reserve（占用一件）—— 此时 _resolve_warehouse_for_order 能命中 warehouse_id=1
    await OrderService.reserve(
        session,
        platform=platform,
        shop_id=shop_id,
        ref=ref,
        lines=[{"item_id": 1, "qty": 1}],
        trace_id=trace_id,
    )

    await session.commit()

    # 4) 从 audit_events 表里查出所有 ORDER 事件
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    category,
                    ref,
                    trace_id,
                    meta->>'event' AS event
                  FROM audit_events
                 WHERE category = 'ORDER'
                   AND ref = :ref
                 ORDER BY id
                """
                ),
                {"ref": ref},
            )
        )
        .mappings()
        .all()
    )

    # 至少应有 ORDER_CREATED 和 ORDER_RESERVED 两条事件
    events = [r["event"] for r in rows]
    assert "ORDER_CREATED" in events
    assert "ORDER_RESERVED" in events

    # 所有这些事件都应带上同一个 trace_id
    trace_ids = {r["trace_id"] for r in rows}
    assert trace_ids == {trace_id}
