# tests/phase2p9/test_soft_reserve_trace_and_lifecycle_v2.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_lifecycle_v2 import OrderLifecycleV2Service
from app.services.soft_reserve_service import SoftReserveService
from app.services.trace_service import TraceService

UTC = timezone.utc


@pytest.mark.pre_pilot
@pytest.mark.asyncio
async def test_soft_reserve_and_lifecycle_v2(
    db_session_like_pg: AsyncSession,
) -> None:
    """
    软预占 + Trace + Lifecycle v2 基线测试（不走订单 / 出库，只测“预占 → 消耗”闭环）

    目标验证：
      1) SoftReserveService.persist 写出 reservations / reservation_lines，带 trace_id；
      2) SoftReserveService.pick_consume 正确更新 reservation_lines.consumed_qty；
      3) TraceService.get_trace(trace_id) 能看到：
           - source="reservation" 事件
           - source="reservation_consumed" 事件
      4) OrderLifecycleV2Service.for_trace_id(trace_id) 的阶段里：
           - key="reserved" 的阶段 present=True
           - key="reserved_consumed" 的阶段 present=True
    """

    session: AsyncSession = db_session_like_pg
    soft_reserve = SoftReserveService()
    trace_svc = TraceService(session)
    lifecycle_svc = OrderLifecycleV2Service(session)

    # 基本业务键（不依赖真实订单表）
    platform = "PDD"
    shop_id = "1"
    warehouse_id = 1
    ref = "ORD:PDD:1:SOFT-TRACE-001"
    trace_id = "TRACE-SOFT-RESERVE-1"

    # 为避免旧数据干扰，清理相关表（只清软预占相关）
    await session.execute(text("DELETE FROM reservation_lines"))
    await session.execute(text("DELETE FROM reservations"))

    # ---------- 1. 软预占 persist ----------
    # 建一张 soft reserve：item_id=1, qty=5
    lines = [{"item_id": 1, "qty": 5}]
    expire_minutes = 30
    now = datetime(2025, 1, 10, 10, 0, tzinfo=UTC)

    r1 = await soft_reserve.persist(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        ref=ref,
        lines=lines,
        expire_at=expire_minutes,
        trace_id=trace_id,
    )

    assert r1.get("status") == "OK"
    reservation_id = int(r1.get("reservation_id") or 0)
    assert reservation_id > 0

    # ---------- 2. 软预占消费 pick_consume ----------
    r2 = await soft_reserve.pick_consume(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        ref=ref,
        occurred_at=now,
        trace_id=trace_id,
    )
    # pick_consume 返回的结构内部细节不强要求，只要不报错就行
    assert r2.get("status") in (None, "OK", "CONSUMED", "PARTIAL", "NOOP")

    # ---------- 3. 校验 reservation_lines.consumed_qty 已经更新 ----------
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT item_id, qty, consumed_qty
                  FROM reservation_lines
                 WHERE reservation_id = :rid
                 ORDER BY id
                 LIMIT 1
                """
                ),
                {"rid": reservation_id},
            )
        )
        .mappings()
        .first()
    )

    assert row is not None, "reservation_lines 里至少应有一条记录"
    assert int(row["item_id"]) == 1
    qty = int(row["qty"] or 0)
    consumed = int(row["consumed_qty"] or 0)
    assert qty == 5
    assert consumed == 5, "pick_consume 后，应当把 consumed_qty 补齐到预占数量"

    # ---------- 4. TraceService：检查 reservation + reservation_consumed 事件 ----------
    trace_result = await trace_svc.get_trace(trace_id)
    events = trace_result.events

    assert any(
        e.source == "reservation" for e in events
    ), "Trace 中应当存在 source='reservation' 的事件"
    assert any(
        e.source == "reservation_consumed" for e in events
    ), "Trace 中应当存在 source='reservation_consumed' 的事件"

    # 附加检查：TraceResult.reservation_consumption 聚合结构中，
    # 对于我们的 reservation_id + item_id=1，qty 与 consumed 应当相等。
    consumption = trace_result.reservation_consumption
    # 把所有 reservation_id/item_id 拉平检查，只要有一条符合就行
    matched = False
    for _rid, by_item in consumption.items():
        for item_id, rec in by_item.items():
            if item_id != 1:
                continue
            if rec.get("qty") == 5 and rec.get("consumed") == 5:
                matched = True
                break
        if matched:
            break
    assert (
        matched
    ), "TraceResult.reservation_consumption 中应当能看到 item=1 qty=5 consumed=5 的汇总"

    # ---------- 5. Lifecycle v2：检查 reserved / reserved_consumed 阶段 ----------
    stages = await lifecycle_svc.for_trace_id(trace_id)
    stage_by_key = {s.key: s for s in stages}

    reserved = stage_by_key.get("reserved")
    reserved_consumed = stage_by_key.get("reserved_consumed")

    assert reserved is not None, "生命周期中应当有 reserved 阶段"
    assert reserved.present is True, "reserved 阶段 present 应为 True"

    assert reserved_consumed is not None, "生命周期中应当有 reserved_consumed 阶段"
    assert reserved_consumed.present is True, "reserved_consumed 阶段 present 应为 True"

    # shipped / outbound 等阶段在本测试场景下可以不存在，不做硬性要求。
