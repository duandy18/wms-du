# tests/services/test_order_service.py
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item
from tests.services._helpers import ensure_store

from app.oms.services.order_service import OrderService
from app.wms.outbound.services.pick_task_commit_ship import commit_ship
from app.wms.outbound.services.pick_task_commit_ship_handoff import expected_handoff_code_from_task_ref
from app.wms.stock.services.lots import ensure_internal_lot_singleton

UTC = timezone.utc
pytestmark = pytest.mark.contract


async def _ensure_order_row(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
    warehouse_id: int,
    trace_id: str,
) -> str:
    """
    Phase 5+ 最小订单头（不再写 orders.warehouse_id）：
    - orders: 只写 platform/shop_id/ext_order_no/trace_id/created_at
    - order_fulfillment: 写 actual_warehouse_id + fulfillment_status（让其可进入拣货主线）
    """
    plat = platform.upper()
    now = datetime.now(UTC)

    store_id = await ensure_store(
        session,
        platform=plat,
        shop_id=shop_id,
        name=f"UT-{plat}-{shop_id}",
    )

    row = await session.execute(
        text(
            """
            INSERT INTO orders (
                platform,
                shop_id,
                store_id,
                ext_order_no,
                status,
                trace_id,
                created_at,
                updated_at
            )
            VALUES (
                :p,
                :s,
                :store_id,
                :o,
                'CREATED',
                :tid,
                :created_at,
                :created_at
            )
            ON CONFLICT ON CONSTRAINT uq_orders_platform_shop_ext DO UPDATE
              SET store_id = EXCLUDED.store_id,
                  trace_id = COALESCE(EXCLUDED.trace_id, orders.trace_id),
                  updated_at = EXCLUDED.updated_at
            RETURNING id
            """
        ),
        {
            "p": plat,
            "s": shop_id,
            "store_id": int(store_id),
            "o": ext_order_no,
            "tid": trace_id,
            "created_at": now,
        },
    )
    order_id = int(row.scalar_one())
    assert order_id > 0

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
              NULL,
              :awid,
              'SERVICE_ASSIGNED',
              NULL,
              :at
            )
            ON CONFLICT (order_id) DO UPDATE
               SET actual_warehouse_id = EXCLUDED.actual_warehouse_id,
                   fulfillment_status  = EXCLUDED.fulfillment_status,
                   blocked_reasons     = NULL,
                   updated_at          = EXCLUDED.updated_at
            """
        ),
        {"oid": int(order_id), "awid": int(warehouse_id), "at": now},
    )

    return f"ORD:{plat}:{shop_id}:{ext_order_no}"


async def _ensure_internal_lot_for_none_item(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    source_receipt_id: int,
    source_line_no: int,
) -> int:
    """
    Phase M-5 / DB 事实（终态合同）：
    - stocks_lot.lot_id NOT NULL（不存在 NULL 槽位）
    - “非批次商品”依然必须落在某个真实 lot_id 上，使用 INTERNAL lot 表达：
        lot_code_source='INTERNAL' 且 lot_code IS NULL
    - INTERNAL lot 是 (warehouse_id,item_id) 单例（partial unique index），
      source_receipt_id/source_line_no 仅作为可选 provenance（要求成对填充），不参与唯一性锚点。

    返回 INTERNAL lot_id。
    """
    return await ensure_internal_lot_singleton(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        source_receipt_id=int(source_receipt_id),
        source_line_no=int(source_line_no),
    )


@pytest.mark.asyncio
async def test_pick_task_commit_writes_shipment_reason(session: AsyncSession):
    """
    硬防线：通过 pick_task commit 出库写入的 stock_ledger.reason 必须是 SHIPMENT。

    该用例覆盖：
    - enter_pickable（OrderService.reserve）生成 pick_task + pick_task_lines
    - commit_ship 唯一裁决点：扣库存 + 写 ledger + 写 outbound_commits_v2

    Phase M-5 / DB 事实：
    - stocks_lot.lot_id NOT NULL（不存在 NULL 槽位）
    - 非批次商品用 INTERNAL lot（lots.lot_code 可能为 NULL）承载
    """
    wh, item = 1, 93003  # 用 fresh NONE item，避免命中 baseline 中可能已被提升为 REQUIRED 的旧 id

    await ensure_wh_loc_item(session, wh=wh, loc=1, item=item)

    # 为“非批次商品”准备一个 INTERNAL lot 槽位，并 seed qty=10
    # INTERNAL lot 为 (warehouse,item) 单例；source_* 仅作为可选 provenance（成对填充）
    lot_id = await _ensure_internal_lot_for_none_item(
        session,
        warehouse_id=wh,
        item_id=item,
        source_receipt_id=9000001,
        source_line_no=1,
    )
    await session.execute(
        text(
            """
            INSERT INTO stocks_lot(item_id, warehouse_id, lot_id, qty)
            VALUES (:item_id, :wid, :lot_id, 10)
            ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot
            DO UPDATE SET qty = EXCLUDED.qty
            """
        ),
        {"item_id": int(item), "wid": int(wh), "lot_id": int(lot_id)},
    )
    await session.flush()

    platform = "TB"
    shop_id = "TEST"

    # ✅ 用例级唯一 ref，避免命中 outbound_commits_v2 幂等短路
    uniq = uuid4().hex[:10]
    ext_order_no = f"UT-LEDGER-REASON-SHIPMENT-{uniq}"
    trace_id = f"TRACE-{ext_order_no}"

    order_ref = await _ensure_order_row(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        warehouse_id=wh,
        trace_id=trace_id,
    )

    # enter_pickable：生成 pick_task（不触库存）
    r = await OrderService.reserve(
        session,
        platform=platform,
        shop_id=shop_id,
        ref=order_ref,
        lines=[{"item_id": int(item), "qty": 1}],
        trace_id=trace_id,
    )
    assert r.get("status") == "OK"

    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM pick_tasks
                 WHERE ref = :ref AND warehouse_id = :wid
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"ref": order_ref, "wid": int(wh)},
        )
    ).first()
    assert row, "pick_task not created"
    task_id = int(row[0])

    # picked_qty=req_qty（无 diff）
    await session.execute(
        text(
            """
            UPDATE pick_task_lines
               SET picked_qty = req_qty,
                   updated_at = now()
             WHERE task_id = :tid
            """
        ),
        {"tid": task_id},
    )
    await session.flush()

    handoff = expected_handoff_code_from_task_ref(ref=order_ref)
    assert handoff, "invalid handoff code"

    result = await commit_ship(
        session,
        task_id=task_id,
        platform=platform,
        shop_id=shop_id,
        handoff_code=handoff,
        trace_id=trace_id,
        allow_diff=False,
    )
    assert result.get("status") == "OK"
    assert result.get("idempotent") is False, f"unexpected idempotent short-circuit: {result}"

    await session.flush()

    row2 = (
        await session.execute(
            text(
                """
                SELECT reason, ref, trace_id, delta
                  FROM stock_ledger
                 WHERE ref = :ref
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"ref": order_ref},
        )
    ).first()
    assert row2 is not None, f"no stock_ledger written for ref={order_ref}"

    reason, ref2, trace2, delta = row2
    assert str(ref2) == order_ref
    assert str(reason) == "SHIPMENT"
    assert int(delta) < 0
    if trace2 is not None:
        assert str(trace2) == trace_id
