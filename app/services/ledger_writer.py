from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_ledger import StockLedger


def _canon_reason(reason: str) -> Optional[str]:
    """
    将各种 reason/alias 归一到稳定口径：
    RECEIPT / SHIPMENT / ADJUSTMENT
    """
    r = (reason or "").strip().upper()
    if not r:
        return None

    if r in {"RECEIPT", "INBOUND", "RECEIVE", "RETURN", "RETURN_IN", "RETURN_CUSTOMER", "RMA_IN"}:
        return "RECEIPT"

    if r in {
        "SHIPMENT",
        "SHIP",
        "OUTBOUND",
        "OUTBOUND_SHIP",
        "OUTBOUND_COMMIT",
        "DISPATCH",
        "RETURN_OUT",
        "RTV",
    }:
        return "SHIPMENT"

    if r in {"ADJUSTMENT", "ADJUST", "COUNT", "PICK", "PACK", "SCRAP", "CORRECT", "MANUAL_ADJUST"}:
        return "ADJUSTMENT"

    return None


async def write_ledger(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: str,
    reason: str,
    sub_reason: Optional[str] = None,
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
    幂等台账写入（只增不改）：
    - 幂等唯一键以 DB 约束 uq_ledger_wh_batch_item_reason_ref_line 为准
    - 返回 0 表示命中幂等，否则返回新 id

    可解释性补全（冲突时仅补齐缺字段，不修改核心事实字段）：
    - 由于幂等键不包含 sub_reason/trace_id/reason_canon，历史可能先写入“缺字段”记录；
      再写同键时会触发 ON CONFLICT。
    - 过去 DO NOTHING 会导致缺字段永远补不回来。
    - 现在：先 DO NOTHING 保持幂等返回语义；若命中冲突，再做一次 UPDATE 补全缺字段。
    - 并且将空字符串视为缺失（NULLIF）。
    """
    reason_canon = _canon_reason(reason)

    base_values = dict(
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        batch_code=str(batch_code),
        reason=str(reason),
        reason_canon=reason_canon,
        sub_reason=sub_reason,
        ref=str(ref),
        ref_line=int(ref_line),
        delta=int(delta),
        after_qty=int(after_qty),
        occurred_at=occurred_at,
        trace_id=trace_id,
        production_date=production_date,
        expiry_date=expiry_date,
    )

    # 1) 先尝试插入：冲突就不插入 -> returning None -> 语义返回 0
    ins = (
        pg_insert(StockLedger)
        .values(**base_values)
        .on_conflict_do_nothing(constraint="uq_ledger_wh_batch_item_reason_ref_line")
        .returning(StockLedger.id)
    )

    res = await session.execute(ins)
    new_id = res.scalar_one_or_none()
    if new_id is not None:
        return int(new_id)

    # 2) 冲突命中：补齐缺字段（不改变核心事实字段），最终仍返回 0
    # 把空串当成缺失：NULLIF(col, '')
    old_reason_canon = sa.func.nullif(StockLedger.reason_canon, "")
    old_sub_reason = sa.func.nullif(StockLedger.sub_reason, "")
    old_trace_id = sa.func.nullif(StockLedger.trace_id, "")

    # 仅当本次传入有值时，才有必要尝试补齐（减少无意义 update）
    need_patch = any(
        [
            bool((reason_canon or "").strip()) if isinstance(reason_canon, str) else reason_canon is not None,
            bool((sub_reason or "").strip()) if isinstance(sub_reason, str) else sub_reason is not None,
            bool((trace_id or "").strip()) if isinstance(trace_id, str) else trace_id is not None,
            production_date is not None,
            expiry_date is not None,
        ]
    )
    if not need_patch:
        return 0

    upd_values = {
        "reason_canon": sa.func.coalesce(old_reason_canon, reason_canon),
        "sub_reason": sa.func.coalesce(old_sub_reason, sub_reason),
        "trace_id": sa.func.coalesce(old_trace_id, trace_id),
        "production_date": sa.func.coalesce(StockLedger.production_date, production_date),
        "expiry_date": sa.func.coalesce(StockLedger.expiry_date, expiry_date),
    }

    await session.execute(
        sa.update(StockLedger)
        .where(
            StockLedger.warehouse_id == int(warehouse_id),
            StockLedger.item_id == int(item_id),
            StockLedger.batch_code == str(batch_code),
            StockLedger.reason == str(reason),
            StockLedger.ref == str(ref),
            StockLedger.ref_line == int(ref_line),
        )
        .values(**upd_values)
    )

    return 0
