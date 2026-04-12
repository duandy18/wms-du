# app/wms/ledger/services/ledger_writer.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.ledger.models.stock_ledger import StockLedger
from app.wms.stock.services.lot_guard import assert_lot_belongs_to


# ========================
# Phase M-2:
# idempotency key is pure lot_id
# ========================


def _idem_constraint_name() -> str:
    return "uq_ledger_wh_lot_item_reason_ref_line"


def _canon_reason(reason: str) -> Optional[str]:
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


def _need_patch(
    *,
    reason_canon: Optional[str],
    sub_reason: Optional[str],
    trace_id: Optional[str],
    event_id: Optional[int],
    production_date: Optional[date],
    expiry_date: Optional[date],
) -> bool:
    return any(
        [
            reason_canon is not None,
            sub_reason is not None,
            trace_id is not None,
            event_id is not None,
            production_date is not None,
            expiry_date is not None,
        ]
    )


def _build_patch_where(
    *,
    warehouse_id: int,
    item_id: int,
    lot_id: int,
    reason: str,
    ref: str,
    ref_line: int,
):
    return (
        (StockLedger.warehouse_id == int(warehouse_id)),
        (StockLedger.item_id == int(item_id)),
        (StockLedger.lot_id == int(lot_id)),
        (StockLedger.reason == str(reason)),
        (StockLedger.ref == str(ref)),
        (StockLedger.ref_line == int(ref_line)),
    )


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
    event_id: Optional[int] = None,
    production_date: Optional[date] = None,
    expiry_date: Optional[date] = None,
    lot_id: int,
) -> int:
    """
    幂等台账写入（只增不改）
    终态：lot_id 为唯一结构锚点

    Phase 3 结构收口：
    - 只有 reason_canon='RECEIPT' 的台账行允许携带 production/expiry（canonical 快照）
    - 其他 reason 一律禁止携带日期（由 DB check + 这里的写入规范共同保证）

    当前补充：
    - event_id 为统一 WMS 业务事件锚点
    - trace_id 为技术链路锚点

    注意：
    - batch_code 为历史兼容入参（展示码 lots.lot_code），stock_ledger 表终态不落 batch_code 列。
    """

    await assert_lot_belongs_to(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        lot_id=lot_id,
    )

    reason_canon = _canon_reason(reason)
    _ = _norm_batch_code(batch_code)  # 兼容归一：仅用于上游语义/日志；不落 stock_ledger 表

    # ---- Phase 3: enforce "dates only on RECEIPT" at write boundary ----
    if reason_canon != "RECEIPT":
        production_date = None
        expiry_date = None

    base_values = dict(
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        lot_id=int(lot_id),
        reason=str(reason),
        reason_canon=reason_canon,
        sub_reason=sub_reason,
        ref=str(ref),
        ref_line=int(ref_line),
        delta=int(delta),
        after_qty=int(after_qty),
        occurred_at=occurred_at,
        trace_id=trace_id,
        event_id=event_id,
        production_date=production_date,
        expiry_date=expiry_date,
    )

    tbl = StockLedger.__table__

    ins = (
        pg_insert(tbl)
        .values(**base_values)
        .on_conflict_do_nothing(constraint=_idem_constraint_name())
        .returning(tbl.c.id)
    )

    res = await session.execute(ins)
    new_id = res.scalar_one_or_none()
    if new_id is not None:
        return int(new_id)

    if not _need_patch(
        reason_canon=reason_canon,
        sub_reason=sub_reason,
        trace_id=trace_id,
        event_id=event_id,
        production_date=production_date,
        expiry_date=expiry_date,
    ):
        return 0

    upd_values = {
        "reason_canon": sa.func.coalesce(StockLedger.reason_canon, reason_canon),
        "sub_reason": sa.func.coalesce(StockLedger.sub_reason, sub_reason),
        "trace_id": sa.func.coalesce(StockLedger.trace_id, trace_id),
        "event_id": sa.func.coalesce(StockLedger.event_id, event_id),
        # 日期快照不可变：只允许 NULL -> 值（coalesce 保证）
        "production_date": sa.func.coalesce(StockLedger.production_date, production_date),
        "expiry_date": sa.func.coalesce(StockLedger.expiry_date, expiry_date),
    }

    await session.execute(
        sa.update(StockLedger)
        .where(
            *_build_patch_where(
                warehouse_id=warehouse_id,
                item_id=item_id,
                lot_id=lot_id,
                reason=reason,
                ref=ref,
                ref_line=ref_line,
            )
        )
        .values(**upd_values)
    )

    return 0
