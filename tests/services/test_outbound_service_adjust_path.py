from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.outbound_service import OutboundService


async def _pick_one_stock_slot(session: AsyncSession):
    """
    从 stocks 中挑一个 (item_id, warehouse_id, batch_code, sum_qty)。
    若没有可用，则跳过测试。
    """
    row = await session.execute(
        text(
            """
            SELECT item_id, warehouse_id, batch_code, SUM(qty) AS qty
            FROM stocks
            WHERE qty > 0 AND batch_code IS NOT NULL
            GROUP BY item_id, warehouse_id, batch_code
            ORDER BY item_id, warehouse_id, batch_code
            LIMIT 1
            """
        )
    )
    r = row.first()
    if not r:
        pytest.skip("当前基线中没有带 batch_code 的 stocks 记录")
    return int(r[0]), int(r[1]), str(r[2]), int(r[3])


@pytest.mark.asyncio
async def test_outbound_commit_merges_lines_and_writes_ledger(session: AsyncSession):
    """
    同一 (item,wh,batch) 多行出库，应合并为一次扣减：
      - results.committed_lines == 1
      - total_qty == 汇总 qty
      - stock_ledger 中对应 ref 的 delta 总和 == -total_qty
    """
    item_id, warehouse_id, batch_code, qty_sum = await _pick_one_stock_slot(session)
    if qty_sum < 5:
        pytest.skip(f"库存太少 qty_sum={qty_sum}, 不适合测试总扣减为 5")

    order_id = "OUT-TEST-1"
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
            SELECT COALESCE(SUM(delta), 0)
            FROM stock_ledger
            WHERE ref = :ref
              AND reason = 'OUTBOUND_SHIP'
              AND item_id = :item_id
              AND warehouse_id = :warehouse_id
              AND batch_code = :batch_code
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
    """
    item_id, warehouse_id, batch_code, qty_sum = await _pick_one_stock_slot(session)
    if qty_sum < 3:
        pytest.skip(f"库存太少 qty_sum={qty_sum}, 不适合测试")

    order_id = "OUT-TEST-2"
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
            SELECT COALESCE(SUM(delta), 0)
            FROM stock_ledger
            WHERE ref = :ref
              AND reason = 'OUTBOUND_SHIP'
              AND item_id = :item_id
              AND warehouse_id = :warehouse_id
              AND batch_code = :batch_code
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
    # 理论上 total_qty 应该为 0 或 <= 0，表示没有额外扣减
    assert r2["total_qty"] <= 0

    row = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(delta), 0)
            FROM stock_ledger
            WHERE ref = :ref
              AND reason = 'OUTBOUND_SHIP'
              AND item_id = :item_id
              AND warehouse_id = :warehouse_id
              AND batch_code = :batch_code
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
