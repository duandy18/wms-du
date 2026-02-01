# tests/services/soft_reserve/test_outbound_batch_merge_soft.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.outbound_service import OutboundService

UTC = timezone.utc

pytestmark = pytest.mark.asyncio


async def _seed_batch_and_stock(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str,
    qty: int,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO batches (item_id, warehouse_id, batch_code, expiry_date)
            VALUES (:item, :wh, :code, NULL)
            ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
            """
        ),
        {"item": item_id, "wh": warehouse_id, "code": batch_code},
    )
    await session.execute(
        text(
            """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
            VALUES (:item, :wh, :code, :qty)
            ON CONFLICT ON CONSTRAINT uq_stocks_item_wh_batch
            DO UPDATE SET qty = EXCLUDED.qty
            """
        ),
        {"item": item_id, "wh": warehouse_id, "code": batch_code, "qty": qty},
    )
    await session.commit()


@pytest.mark.asyncio
async def test_outbound_merge_duplicate_lines_in_single_payload(session: AsyncSession):
    """
    同一 payload 中重复的 (item, warehouse_id, batch_code) 仅按合并量扣减一次。

    场景：
      - 初始库存 10；
      - outbound payload 中两行：
          qty=1
          qty=2
      - 期望总扣减为 3，ledger 中该 ref 的负向合计 delta = -3。
    """
    svc = OutboundService()

    order_id = "OB-MERGE-1"
    item_id = 4001
    warehouse_id = 1
    batch_code = "B-MERGE-1"

    await _seed_batch_and_stock(
        session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        batch_code=batch_code,
        qty=10,
    )

    lines = [
        {"item_id": item_id, "warehouse_id": warehouse_id, "batch_code": batch_code, "qty": 1},
        {"item_id": item_id, "warehouse_id": warehouse_id, "batch_code": batch_code, "qty": 2},
    ]

    result = await svc.commit(
        session=session,
        order_id=order_id,
        lines=lines,
        occurred_at=datetime.now(UTC),
    )
    assert result["status"] == "OK"

    row = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(delta), 0)
              FROM stock_ledger
             WHERE ref = :ref
               AND item_id = :item
               AND warehouse_id = :wh
               AND batch_code = :code
               AND delta < 0
            """
        ),
        {"ref": str(order_id), "item": item_id, "wh": warehouse_id, "code": batch_code},
    )
    total_delta = int(row.scalar() or 0)
    assert total_delta == -3

    row = await session.execute(
        text(
            """
            SELECT SUM(qty)
              FROM stocks
             WHERE item_id = :item
               AND warehouse_id = :wh
               AND batch_code = :code
            """
        ),
        {"item": item_id, "wh": warehouse_id, "code": batch_code},
    )
    on_hand = row.scalar() or 0
    assert int(on_hand) == 7
