# tests/services/test_outbound_ledger_consistency.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.outbound_service import OutboundService

UTC = timezone.utc

pytestmark = pytest.mark.asyncio


async def _seed_minimal_order_for_outbound(
    session: AsyncSession,
) -> tuple[str, int, int, str]:
    """
    为出库写台账准备一条最小订单头（Phase 5+）：

    - platform = 'PDD'
    - shop_id = 'UT-SHOP'
    - actual_warehouse_id = 1（写入 order_fulfillment）
    - item_id = 1
    - ext_order_no = 'LEDGER-OUT-1'
    - ref = ORD:{platform}:{shop_id}:{ext_order_no}
    """
    platform = "PDD"
    shop_id = "UT-SHOP"
    wh_id = 1
    item_id = 1
    ext_order_no = "LEDGER-OUT-1"
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"
    trace_id = "TRACE-LEDGER-OUT-1"

    await session.execute(
        text(
            """
            INSERT INTO items (id, sku, name)
            VALUES (:item_id, :sku, :name)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"item_id": item_id, "sku": "SKU-0001", "name": "UT-ITEM-1"},
    )

    # orders（不再包含 warehouse_id）
    row = await session.execute(
        text(
            """
            INSERT INTO orders (
                platform,
                shop_id,
                ext_order_no,
                status,
                trace_id,
                created_at,
                updated_at
            )
            VALUES (
                :platform,
                :shop_id,
                :ext_order_no,
                'CREATED',
                :trace_id,
                now(),
                now()
            )
            ON CONFLICT ON CONSTRAINT uq_orders_platform_shop_ext DO UPDATE
              SET status = EXCLUDED.status,
                  trace_id = COALESCE(EXCLUDED.trace_id, orders.trace_id),
                  updated_at = now()
            RETURNING id
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "ext_order_no": ext_order_no,
            "trace_id": trace_id,
        },
    )
    order_id = int(row.scalar_one())
    assert order_id > 0

    # order_fulfillment：写执行仓事实（Phase 5+）
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
              'READY_TO_FULFILL',
              NULL,
              now()
            )
            ON CONFLICT (order_id) DO UPDATE
               SET actual_warehouse_id = EXCLUDED.actual_warehouse_id,
                   fulfillment_status  = EXCLUDED.fulfillment_status,
                   blocked_reasons     = NULL,
                   updated_at          = now()
            """
        ),
        {"oid": int(order_id), "awid": int(wh_id)},
    )

    await session.commit()
    return order_ref, wh_id, item_id, trace_id


async def _pick_one_stock_slot_for_item(session: AsyncSession, *, warehouse_id: int, item_id: int) -> str | None:
    """
    从 stocks 中挑一个 (item_id, warehouse_id) 下 qty>0 的槽位，返回 batch_code（可能为 NULL）。
    强护栏下，非批次商品一般是 NULL 槽位。
    """
    row = (
        await session.execute(
            text(
                """
                SELECT batch_code, qty
                  FROM stocks
                 WHERE warehouse_id = :w
                   AND item_id = :i
                   AND qty > 0
                 ORDER BY id ASC
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id)},
        )
    ).first()
    if not row:
        pytest.skip("no stock slot with qty>0 for item/warehouse in baseline")
    return row[0]


@pytest.mark.asyncio
async def test_outbound_commit_writes_consistent_ledger(session: AsyncSession) -> None:
    """
    验证：出库 commit 之后，台账中的 OUTBOUND_SHIP 记录在维度上与 stocks 槽位一致。

    这里不关心完整业务流程（soft reserve / audit / platform events），只关心：
    - OutboundService.commit 能在当前 schema 下正常运行；
    - 写出来的 stock_ledger 行：
        * reason = 'OUTBOUND_SHIP'
        * warehouse_id / item_id / batch_code|NULL 维度正确
        * delta < 0（出库）
    """
    order_ref, wh_id, item_id, trace_id = await _seed_minimal_order_for_outbound(session)

    batch_code = await _pick_one_stock_slot_for_item(session, warehouse_id=wh_id, item_id=item_id)
    qty_to_ship = 3

    svc = OutboundService()
    lines = [
        {
            "item_id": item_id,
            "batch_code": batch_code,
            "qty": qty_to_ship,
            "warehouse_id": wh_id,
        }
    ]

    occurred_at = datetime.now(UTC)

    result = await svc.commit(
        session=session,
        order_id=order_ref,
        lines=lines,
        occurred_at=occurred_at,
        trace_id=trace_id,
    )
    assert isinstance(result, dict)

    rows = (
        await session.execute(
            text(
                """
                SELECT
                    warehouse_id,
                    item_id,
                    batch_code,
                    reason,
                    ref,
                    delta,
                    after_qty
                  FROM stock_ledger
                 WHERE reason = 'OUTBOUND_SHIP'
                   AND ref = :ref
                 ORDER BY occurred_at, id
                """
            ),
            {"ref": order_ref},
        )
    ).mappings().all()

    assert rows, "expected at least one OUTBOUND_SHIP ledger row for outbound commit"

    for r in rows:
        assert int(r["warehouse_id"]) == wh_id
        assert int(r["item_id"]) == item_id
        assert (r["batch_code"] == batch_code) or (r["batch_code"] is None and batch_code is None)
        assert r["reason"] == "OUTBOUND_SHIP"
        assert int(r["delta"]) < 0
