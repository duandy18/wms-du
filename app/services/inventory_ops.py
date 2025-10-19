# app/services/inventory_ops.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

LEDGER_INSERT_SQL = text(
    """
INSERT INTO ledger (
    item_id, location_id, delta, kind, reason,
    ref, ref_line, batch_id,
    occurred_at, created_at
) VALUES (
    :item_id, :location_id, :delta, :kind, :reason,
    :ref, :ref_line, :batch_id,
    :occurred_at, now()
)
ON CONFLICT (ref, ref_line, kind)
DO NOTHING
RETURNING id, delta;
"""
)

STOCKS_UPSERT_SQL = text(
    """
INSERT INTO stocks (item_id, location_id, qty, updated_at)
VALUES (:item_id, :location_id, :delta, now())
ON CONFLICT (item_id, location_id)
DO UPDATE SET
    qty = stocks.qty + EXCLUDED.qty,
    updated_at = now()
RETURNING id, qty;
"""
)

BATCH_ALLOC_SQL = text(
    """
-- 可选：扣/加批次可用数（如果你的模型用 available_qty）
UPDATE batches
SET available_qty = available_qty + :delta,
    updated_at = now()
WHERE id = :batch_id;
"""
)


async def apply_delta_idempotent(
    session: AsyncSession,
    *,
    item_id: int,
    location_id: int,
    delta: float,
    kind: str,  # INBOUND/PUTAWAY/ADJUST/TRANSFER...
    reason: str | None,
    ref: str,
    ref_line: str | None = None,
    batch_id: int | None = None,
    occurred_at: datetime | None = None,
    touch_batch_available: bool = False,
) -> dict:
    """
    幂等库存变更：
    1) 先尝试写 ledger（ref+ref_line+kind 唯一）；
    2) 若写入成功，再 UPSERT stocks；
    3) 可选同步批次 available_qty；
    4) 若 ledger 冲突（重复回放），不再改 stocks（幂等保证）。
    返回：{ inserted: bool, ledger_id: Optional[int], new_qty: Optional[Decimal], delta: Decimal }
    """
    occurred_at = occurred_at or datetime.utcnow()

    # 1) 尝试插 ledger（幂等入口）
    res_ledger = await session.execute(
        LEDGER_INSERT_SQL,
        dict(
            item_id=item_id,
            location_id=location_id,
            delta=delta,
            kind=kind,
            reason=reason,
            ref=ref,
            ref_line=ref_line,
            batch_id=batch_id,
            occurred_at=occurred_at,
        ),
    )
    row = res_ledger.first()

    if row is None:
        # 幂等命中：ledger 已存在，不重复改 stocks
        return {"inserted": False, "ledger_id": None, "new_qty": None, "delta": 0}

    ledger_id, eff_delta = row[0], row[1]

    # 2) UPSERT stocks
    res_stocks = await session.execute(
        STOCKS_UPSERT_SQL,
        dict(item_id=item_id, location_id=location_id, delta=eff_delta),
    )
    stocks_row = res_stocks.first()
    new_qty = stocks_row[1] if stocks_row else None

    # 3) 可选同步批次可用数
    if touch_batch_available and batch_id:
        await session.execute(BATCH_ALLOC_SQL, dict(delta=eff_delta, batch_id=batch_id))

    return {
        "inserted": True,
        "ledger_id": ledger_id,
        "new_qty": new_qty,
        "delta": eff_delta,
    }
