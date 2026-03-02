from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.outbound_service import OutboundService


async def _pick_one_stock_slot(session: AsyncSession):
    """
    从 stocks_lot 中挑一个 (item_id, warehouse_id, lot_code, sum_qty)。

    - lot_code 来自 lots.lot_code（可能为 NULL：INTERNAL lot 的展示码）
    - 只选 qty > 0 的槽位
    """
    row = await session.execute(
        text(
            """
            SELECT
                sl.item_id,
                sl.warehouse_id,
                lo.lot_code AS batch_code,
                SUM(sl.qty) AS qty
            FROM stocks_lot sl
            LEFT JOIN lots lo ON lo.id = sl.lot_id
            WHERE sl.qty > 0
            GROUP BY sl.item_id, sl.warehouse_id, lo.lot_code
            ORDER BY sl.item_id, sl.warehouse_id, lo.lot_code NULLS FIRST
            LIMIT 1
            """
        )
    )
    r = row.first()
    if not r:
        pytest.skip("当前基线中没有 qty>0 的 stocks_lot 记录")
    return int(r[0]), int(r[1]), r[2], int(r[3])


@pytest.mark.asyncio
async def test_outbound_commit_merges_lines_and_writes_ledger(session: AsyncSession):
    """
    同一 (item,wh,batch) 多行出库，应合并为一次扣减：
      - results.committed_lines == 1
      - total_qty == 汇总 qty
      - stock_ledger 中对应 ref 的 delta 总和 == -total_qty

    终态：stock_ledger 不存在 batch_code 列；展示码来自 lots.lot_code。
    """
    item_id, warehouse_id, batch_code, qty_sum = await _pick_one_stock_slot(session)
    if qty_sum < 5:
        pytest.skip(f"库存太少 qty_sum={qty_sum}, 不适合测试总扣减为 5")

    order_id = "UT:PH3:OUT-TEST-1"
    lines = [
        {"item_id": item_id, "warehouse_id": warehouse_id, "batch_code": batch_code, "qty": 2},
        {"item_id": item_id, "warehouse_id": warehouse_id, "batch_code": batch_code, "qty": 3},
    ]

    svc = OutboundService()
    ts = datetime.now(timezone.utc)

    result = await svc.commit(
        session,
        order_id=order_id,
        lines=lines,
        occurred_at=ts,
    )

    assert result["status"] == "OK"
    assert result["committed_lines"] == 1
    assert result["total_qty"] == 5

    row = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(l.delta), 0)
              FROM stock_ledger l
              LEFT JOIN lots lo ON lo.id = l.lot_id
             WHERE l.ref = :ref
               AND l.reason = 'OUTBOUND_SHIP'
               AND l.item_id = :item_id
               AND l.warehouse_id = :warehouse_id
               AND lo.lot_code IS NOT DISTINCT FROM CAST(:batch_code AS TEXT)
            """
        ),
        {
            "ref": order_id,
            "item_id": item_id,
            "warehouse_id": warehouse_id,
            "batch_code": batch_code,
        },
    )
    total_delta = int(row.scalar() or 0)
    assert total_delta == -5


@pytest.mark.asyncio
async def test_outbound_commit_idempotent_same_payload(session: AsyncSession):
    """
    同一 order_id + 同样 lines 再次调用：
      - 第二次不再额外扣减（delta 总和保持不变）

    终态：stock_ledger 不存在 batch_code 列；展示码来自 lots.lot_code。
    """
    item_id, warehouse_id, batch_code, qty_sum = await _pick_one_stock_slot(session)
    if qty_sum < 3:
        pytest.skip("库存太少 qty_sum={qty_sum}, 不适合测试")

    order_id = "UT:PH3:OUT-TEST-2"
    lines = [
        {"item_id": item_id, "warehouse_id": warehouse_id, "batch_code": batch_code, "qty": 3},
    ]

    svc = OutboundService()
    ts = datetime.now(timezone.utc)

    # 第一次
    r1 = await svc.commit(session, order_id=order_id, lines=lines, occurred_at=ts)
    assert r1["status"] == "OK"

    row = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(l.delta), 0)
              FROM stock_ledger l
              LEFT JOIN lots lo ON lo.id = l.lot_id
             WHERE l.ref = :ref
               AND l.reason = 'OUTBOUND_SHIP'
               AND l.item_id = :item_id
               AND l.warehouse_id = :warehouse_id
               AND lo.lot_code IS NOT DISTINCT FROM CAST(:batch_code AS TEXT)
            """
        ),
        {
            "ref": order_id,
            "item_id": item_id,
            "warehouse_id": warehouse_id,
            "batch_code": batch_code,
        },
    )
    total_delta_1 = int(row.scalar() or 0)
    assert total_delta_1 == -3

    # 第二次同 payload
    r2 = await svc.commit(session, order_id=order_id, lines=lines, occurred_at=ts)
    assert r2["status"] == "OK"
    assert r2["total_qty"] <= 0

    row = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(l.delta), 0)
              FROM stock_ledger l
              LEFT JOIN lots lo ON lo.id = l.lot_id
             WHERE l.ref = :ref
               AND l.reason = 'OUTBOUND_SHIP'
               AND l.item_id = :item_id
               AND l.warehouse_id = :warehouse_id
               AND lo.lot_code IS NOT DISTINCT FROM CAST(:batch_code AS TEXT)
            """
        ),
        {
            "ref": order_id,
            "item_id": item_id,
            "warehouse_id": warehouse_id,
            "batch_code": batch_code,
        },
    )
    total_delta_2 = int(row.scalar() or 0)
    assert total_delta_2 == total_delta_1
