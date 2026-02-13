# tests/services/test_platform_events.py
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.platform_events import handle_event_batch

pytestmark = pytest.mark.contract


async def _ensure_order_for_event(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
    warehouse_id: int,
    trace_id: str,
) -> str:
    """
    为即将处理的平台事件插入一条最小化订单头（带 trace_id），并写入执行仓事实，
    返回标准化订单 ref：ORD:{PLAT}:{shop_id}:{ext_order_no}。

    新世界观（一步到位迁移后）：
      - 订单头在 orders
      - 执行仓事实/履约快照在 order_fulfillment
      - blocked 只保留 blocked_reasons（不保留 detail）
    """
    plat = platform.upper()

    # 1) orders：只写订单头（不写 warehouse_id）
    await session.execute(
        text(
            """
            INSERT INTO orders (
                platform,
                shop_id,
                ext_order_no,
                trace_id,
                created_at
            )
            VALUES (
                :p,
                :s,
                :o,
                :tid,
                now()
            )
            ON CONFLICT ON CONSTRAINT uq_orders_platform_shop_ext DO NOTHING
            """
        ),
        {
            "p": plat,
            "s": shop_id,
            "o": ext_order_no,
            "tid": trace_id,
        },
    )

    # 2) 取 order_id，写 order_fulfillment（执行仓事实）
    row = await session.execute(
        text(
            """
            SELECT id
              FROM orders
             WHERE platform = :p
               AND shop_id = :s
               AND ext_order_no = :o
             LIMIT 1
            """
        ),
        {"p": plat, "s": shop_id, "o": ext_order_no},
    )
    order_id = row.scalar_one_or_none()
    if order_id is None:
        raise RuntimeError("failed to ensure order head for platform event test")

    await session.execute(
        text(
            """
            INSERT INTO order_fulfillment (
                order_id,
                planned_warehouse_id,
                actual_warehouse_id,
                fulfillment_status,
                blocked_reasons,
                updated_at
            )
            VALUES (
                :oid,
                :wid,
                :wid,
                'READY_TO_FULFILL',
                NULL,
                now()
            )
            ON CONFLICT (order_id) DO UPDATE
               SET planned_warehouse_id = EXCLUDED.planned_warehouse_id,
                   actual_warehouse_id  = EXCLUDED.actual_warehouse_id,
                   fulfillment_status   = EXCLUDED.fulfillment_status,
                   blocked_reasons      = NULL,
                   updated_at           = now()
            """
        ),
        {"oid": int(order_id), "wid": int(warehouse_id)},
    )

    return f"ORD:{plat}:{shop_id}:{ext_order_no}"


@pytest.mark.asyncio
async def test_platform_event_basic_flow(session: AsyncSession):
    """
    平台事件 basic flow 合同（升级版）：

    场景：
      - 模拟一个“已支付”事件；
      - 事件中的 order_sn 使用标准订单 ref（ORD:PLAT:shop:ext_order_no）；
      - handle_event_batch 内部会：
          * 解析事件；
          * 调用 Golden Flow（reserve 等）；
          * 写入 event_log。

    本测试只关心：
      - handle_event_batch 能正常返回（不抛异常）；
      - event_log 中至少有一条记录。
    """
    platform = "pdd"
    shop_id = "S1"
    ext_order_no = "O1"
    trace_id = "TRACE-PLATFORM-O1"
    warehouse_id = 1

    # 为该事件准备订单头 + 履约事实，并得到标准订单 ref
    order_ref = await _ensure_order_for_event(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        warehouse_id=warehouse_id,
        trace_id=trace_id,
    )

    # 模拟一个“已支付”事件：
    # order_sn 这里直接使用标准 ref（等价于“经过适配层转换后的结果”）
    ev = [
        {
            "platform": platform,
            "shop_id": shop_id,
            "order_sn": order_ref,
            "status": "PAID",
            "lines": [{"item_id": 3001, "qty": 1}],
        }
    ]

    await handle_event_batch(ev, session=session)

    # 有事件入库（source 由服务内部统一写入）
    row = (await session.execute(text("SELECT COUNT(*) FROM event_log"))).scalar_one()
    assert int(row) >= 1
