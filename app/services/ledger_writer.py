from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_ledger import StockLedger  # 按你项目的路径导入模型


async def write_ledger(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: str,
    reason: str,
    delta: int,
    after_qty: int,
    ref: str,
    ref_line: int = 1,
    occurred_at: Optional[datetime] = None,
    trace_id: Optional[str] = None,
    production_date: Optional[date] = None,
    expiry_date: Optional[date] = None,
) -> int:
    """
    幂等台账写入：

    - 唯一键以数据库现有约束“uq_ledger_wh_batch_item_reason_ref_line”为准：
        (warehouse_id, batch_code, item_id, reason, ref, ref_line)

    - 命中幂等返回 0，否则返回生成的 id

    Phase 3.7-A：
      - 增加 trace_id 写入，用于跨表 trace 聚合；
      - 增加 production_date / expiry_date 写入，便于仅靠 ledger 重建批次生命周期。
    """
    stmt = (
        pg_insert(StockLedger)
        .values(
            warehouse_id=warehouse_id,
            item_id=item_id,
            batch_code=batch_code,
            reason=reason,
            ref=ref,
            ref_line=int(ref_line),
            delta=int(delta),
            after_qty=int(after_qty),
            occurred_at=occurred_at,
            trace_id=trace_id,
            production_date=production_date,
            expiry_date=expiry_date,
        )
        .on_conflict_do_nothing(constraint="uq_ledger_wh_batch_item_reason_ref_line")
        .returning(StockLedger.id)
    )

    res = await session.execute(stmt)
    new_id = res.scalar_one_or_none()
    return int(new_id or 0)
