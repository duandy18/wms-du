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
    为即将处理的平台事件插入一条最小化订单头（带 warehouse_id + trace_id），
    并返回标准化的订单 ref：ORD:{PLAT}:{shop_id}:{ext_order_no}。

    说明：
      - 当前 Golden Flow 要求 OrderService.reserve 只接受 ORD:... 形式的 ref，
        并依赖 orders.warehouse_id 来解析仓库；
      - 实际平台适配层应负责把平台原始 order_sn 转成 ORD ref；
        本测试直接模拟“适配层已经完成转换”的场景。
    """
    plat = platform.upper()
    await session.execute(
        text(
            """
            INSERT INTO orders (
                platform,
                shop_id,
                ext_order_no,
                warehouse_id,
                trace_id,
                created_at
            )
            VALUES (
                :p,
                :s,
                :o,
                :w,
                :tid,
                now()
            )
            ON CONFLICT (platform, shop_id, ext_order_no) DO NOTHING
            """
        ),
        {
            "p": plat,
            "s": shop_id,
            "o": ext_order_no,
            "w": warehouse_id,
            "tid": trace_id,
        },
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
          * 调用 OrderService.reserve（Golden Flow）；
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

    # 为该事件准备一条订单头（带 warehouse_id），并得到标准订单 ref
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
