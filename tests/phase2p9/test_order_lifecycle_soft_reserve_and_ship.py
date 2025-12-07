# tests/phase2p9/test_order_lifecycle_soft_reserve_and_ship.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.order_lifecycle_v2 import OrderLifecycleV2Service
from app.services.ship_service import ShipService
from app.services.soft_reserve_service import SoftReserveService
from app.services.stock_service import StockService
from app.services.trace_service import TraceService

UTC = timezone.utc


@pytest.mark.pre_pilot
@pytest.mark.asyncio
async def test_order_lifecycle_soft_reserve_and_ship(
    db_session_like_pg: AsyncSession,
) -> None:
    """
    订单级最小闭环场景：

      orders(带 trace_id)
        → SoftReserveService.persist  (RESERVED)
        → SoftReserveService.pick_consume（reservation_lines.consumed_qty 补齐）
        → StockService.adjust(SHIPMENT)   (真实出库台账)
        → ShipService.commit              (OUTBOUND/SHIP_COMMIT 审计事件)

    期望 Lifecycle v2 阶段：
      - reserved.present           = True
      - reserved_consumed.present  = True
      - shipped.present            = True

    期望 TraceService 事件：
      - source='reservation'
      - source='reservation_consumed'
      - source='ledger' (SHIPMENT)
      - source='audit'  (OUTBOUND/SHIP_COMMIT)
      - source='order'  (来自 orders.trace_id)
    """

    session: AsyncSession = db_session_like_pg

    stock = StockService()
    soft_reserve = SoftReserveService()
    trace_svc = TraceService(session)
    lifecycle_svc = OrderLifecycleV2Service(session)

    # ------- 业务键定义 -------
    platform = "PDD"
    shop_id = "1"
    ext_order_no = "DEMO-ORDER-LIFECYCLE-1"
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"
    warehouse_id = 1
    item_id = 1
    trace_id = "TRACE-ORDER-LIFECYCLE-1"

    now = datetime(2025, 1, 20, 10, 0, tzinfo=UTC)

    # ------- 0. 清理相关表（局部清理，尽量不动别的域） -------
    # 只清这个测试会用到的表，且对 orders 只按具体键删除
    await session.execute(text("DELETE FROM stock_snapshots"))
    await session.execute(text("DELETE FROM stock_ledger"))
    await session.execute(text("DELETE FROM stocks"))
    await session.execute(text("DELETE FROM batches"))
    await session.execute(text("DELETE FROM reservation_lines"))
    await session.execute(text("DELETE FROM reservations"))
    await session.execute(text("DELETE FROM shipping_records"))
    await session.execute(text("DELETE FROM audit_events"))
    await session.execute(
        text(
            """
            DELETE FROM orders
             WHERE platform = :p
               AND shop_id  = :s
               AND ext_order_no = :o
            """
        ),
        {"p": platform, "s": shop_id, "o": ext_order_no},
    )

    # ------- 1. 插入一条订单头（带 trace_id + warehouse_id） -------
    # 只写 lifecycle/trace 需要的最小字段：platform/shop_id/ext_order_no/warehouse_id/trace_id/created_at
    row = (
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
                    :created_at
                )
                RETURNING id
                """
            ),
            {
                "p": platform,
                "s": shop_id,
                "o": ext_order_no,
                "w": warehouse_id,
                "tid": trace_id,
                "created_at": now,
            },
        )
    ).scalar_one()
    order_id = int(row)
    assert order_id > 0

    # ------- 2. 准备库存：给 item_id=1 入一点货，避免出库报“库存不足” -------
    await stock.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        delta=10,  # 给足 10 件
        reason=MovementType.RECEIPT,
        ref="LIFECYCLE-IN",
        ref_line=1,
        occurred_at=now,
        batch_code="LIFE-BATCH-1",
        production_date=None,
        expiry_date=None,
        trace_id=trace_id,
    )

    # ------- 3. 软预占 persist（RESERVED） -------
    r1 = await soft_reserve.persist(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        ref=order_ref,
        lines=[{"item_id": item_id, "qty": 5}],
        expire_at=30,
        trace_id=trace_id,
    )
    assert r1.get("status") == "OK"
    reservation_id = int(r1.get("reservation_id") or 0)
    assert reservation_id > 0

    # ------- 4. 消耗预占 pick_consume（reservation_lines.consumed_qty 补齐） -------
    r2 = await soft_reserve.pick_consume(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        ref=order_ref,
        occurred_at=now,
        trace_id=trace_id,
    )
    assert r2.get("status") in (None, "OK", "CONSUMED", "PARTIAL", "NOOP")

    # ------- 5. 真实出库台账：扣 5 件（SHIPMENT） -------
    out_ts = now
    await stock.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        delta=-5,
        reason=MovementType.SHIPMENT,  # Lifecycle v2 会把 SHIPMENT 视为 shipped 证据
        ref=order_ref,
        ref_line=1,
        occurred_at=out_ts,
        batch_code="LIFE-BATCH-1",
        trace_id=trace_id,
    )

    # ------- 6. 发运审计事件：OUTBOUND/SHIP_COMMIT + shipping_records -------
    ship_svc = ShipService(session)
    meta = {
        "platform": platform,
        "shop_id": shop_id,
        "warehouse_id": warehouse_id,
        "occurred_at": out_ts.isoformat(),
        "carrier_code": "FAKE",
        "carrier_name": "Fake Express",
        "tracking_no": f"FAKE-{ext_order_no}",
        "weight_kg": 1.23,
        "flow": "OUTBOUND",
        "event": "SHIP_COMMIT",
    }

    audit_res = await ship_svc.commit(
        ref=order_ref,
        platform=platform,
        shop_id=shop_id,
        trace_id=trace_id,
        meta=meta,
    )
    assert audit_res.get("ok") is True

    # shipping_records：写一条 DELIVERED，用于 lifecycle 的 delivered 阶段（可选）
    await session.execute(
        text(
            """
            INSERT INTO shipping_records (
                order_ref,
                platform,
                shop_id,
                warehouse_id,
                carrier_code,
                carrier_name,
                tracking_no,
                trace_id,
                weight_kg,
                gross_weight_kg,
                packaging_weight_kg,
                cost_estimated,
                cost_real,
                delivery_time,
                status,
                error_code,
                error_message,
                meta
            )
            VALUES (
                :order_ref,
                :platform,
                :shop_id,
                :warehouse_id,
                :carrier_code,
                :carrier_name,
                :tracking_no,
                :trace_id,
                NULL,
                :gross_weight_kg,
                NULL,
                NULL,
                NULL,
                :delivery_time,
                :status,
                NULL,
                NULL,
                '{}'::jsonb
            )
            """
        ),
        {
            "order_ref": order_ref,
            "platform": platform,
            "shop_id": shop_id,
            "warehouse_id": warehouse_id,
            "carrier_code": "FAKE",
            "carrier_name": "Fake Express",
            "tracking_no": f"FAKE-{ext_order_no}",
            "trace_id": trace_id,
            "gross_weight_kg": 1.23,
            "delivery_time": now,
            "status": "DELIVERED",
        },
    )

    # ------- 7. 校验 reservation_lines.consumed_qty 与 qty 一致 -------
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
    assert row is not None
    assert int(row["item_id"]) == item_id
    assert int(row["qty"] or 0) == 5
    assert int(row["consumed_qty"] or 0) == 5

    # ------- 8. TraceService：检查关键事件源 -------
    trace_result = await trace_svc.get_trace(trace_id)
    sources = {e.source for e in trace_result.events}

    # 核心期望：至少包含这些 source
    assert "order" in sources, "应当有 source='order' 的事件（来自 orders.trace_id）"
    assert "reservation" in sources, "应当有 source='reservation' 的事件"
    assert "reservation_consumed" in sources, "应当有 source='reservation_consumed' 的事件"
    assert "ledger" in sources, "应当有 source='ledger' 的事件（SHIPMENT 出库）"
    assert "audit" in sources, "应当有 source='audit' 的事件（OUTBOUND/SHIP_COMMIT）"

    # ------- 9. Lifecycle v2：检查 reserved / reserved_consumed / shipped / delivered 阶段 -------
    stages = await lifecycle_svc.for_trace_id(trace_id)
    stage_by_key = {s.key: s for s in stages}

    reserved = stage_by_key.get("reserved")
    reserved_consumed = stage_by_key.get("reserved_consumed")
    shipped = stage_by_key.get("shipped")
    delivered = stage_by_key.get("delivered")  # 可能存在（基于 shipping_records）

    assert reserved is not None and reserved.present, "reserved 阶段应存在且 present=True"
    assert (
        reserved_consumed is not None and reserved_consumed.present
    ), "reserved_consumed 阶段应存在且 present=True"
    assert shipped is not None and shipped.present, "shipped 阶段应存在且 present=True"

    # delivered 阶段：有 shipping_records(status=DELIVERED) 就应被注入
    assert delivered is not None and delivered.present, "delivered 阶段应存在且 present=True"
