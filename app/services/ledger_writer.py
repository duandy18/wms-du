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


def _norm_batch_code(batch_code: Optional[str]) -> Optional[str]:
    if batch_code is None:
        return None
    s = str(batch_code).strip()
    return s or None


def _batch_key(batch_code: Optional[str]) -> str:
    bc = _norm_batch_code(batch_code)
    return bc if bc is not None else "__NULL_BATCH__"


async def write_ledger(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: Optional[str],
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

    ✅ 无批次槽位支持：
    - batch_code 允许为 NULL（表示“无批次”）
    - DB 侧用生成列 batch_code_key = COALESCE(batch_code,'__NULL_BATCH__') 参与幂等唯一性
    """
    reason_canon = _canon_reason(reason)
    bc_norm = _norm_batch_code(batch_code)

    base_values = dict(
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        batch_code=bc_norm,  # ✅ may be NULL
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
    old_reason_canon = sa.func.nullif(StockLedger.reason_canon, "")
    old_sub_reason = sa.func.nullif(StockLedger.sub_reason, "")
    old_trace_id = sa.func.nullif(StockLedger.trace_id, "")

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

    # ✅ 用 batch_code_key 让 NULL 也能稳定命中同一幂等行
    await session.execute(
        sa.update(StockLedger)
        .where(
            StockLedger.warehouse_id == int(warehouse_id),
            StockLedger.item_id == int(item_id),
            StockLedger.batch_code_key == _batch_key(bc_norm),
            StockLedger.reason == str(reason),
            StockLedger.ref == str(ref),
            StockLedger.ref_line == int(ref_line),
        )
        .values(**upd_values)
    )

    return 0
