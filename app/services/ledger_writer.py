# app/services/ledger_writer.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_ledger import StockLedger
from app.services.lot_guard import assert_lot_belongs_to


# ========================
# Phase 4A-1: centralized anchors
# - idempotency key includes lot_id_key (COALESCE(lot_id,0))
# - stocks remain batch-world (unchanged)
# ========================


def _idem_constraint_name() -> str:
    """
    当前幂等唯一约束名（Phase 4A-1 切换到 lot_id_key + batch_code_key）。
    """
    return "uq_ledger_wh_lot_batch_item_reason_ref_line"


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


def _batch_key(batch_code: Optional[str]) -> str:
    bc = _norm_batch_code(batch_code)
    return bc if bc is not None else "__NULL_BATCH__"


def _lot_key(lot_id: Optional[int]) -> int:
    return int(lot_id) if lot_id is not None else 0


def _need_patch(
    *,
    reason_canon: Optional[str],
    sub_reason: Optional[str],
    trace_id: Optional[str],
    production_date: Optional[date],
    expiry_date: Optional[date],
) -> bool:
    return any(
        [
            bool((reason_canon or "").strip()) if isinstance(reason_canon, str) else reason_canon is not None,
            bool((sub_reason or "").strip()) if isinstance(sub_reason, str) else sub_reason is not None,
            bool((trace_id or "").strip()) if isinstance(trace_id, str) else trace_id is not None,
            production_date is not None,
            expiry_date is not None,
        ]
    )


def _build_patch_where(
    *,
    warehouse_id: int,
    item_id: int,
    batch_code_norm: Optional[str],
    lot_id: Optional[int],
    reason: str,
    ref: str,
    ref_line: int,
):
    """
    Phase 4A-1:
    where 锚点切换为 (warehouse_id, item_id, lot_id_key, batch_code_key, reason, ref, ref_line)
    与 DB 幂等唯一约束保持 1:1 对齐。
    """
    return (
        (StockLedger.warehouse_id == int(warehouse_id)),
        (StockLedger.item_id == int(item_id)),
        (StockLedger.lot_id_key == _lot_key(lot_id)),
        (StockLedger.batch_code_key == _batch_key(batch_code_norm)),
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
    production_date: Optional[date] = None,
    expiry_date: Optional[date] = None,
    lot_id: Optional[int] = None,  # Phase 3+: lot shadow dimension (Phase 4A-1 participates in idempotency key)
) -> int:
    """
    幂等台账写入（只增不改）

    Phase 4A-1:
    - DB 幂等唯一键升级为 lot_id_key + batch_code_key 复合键
    - ON CONFLICT 绑定新约束名
    - patch where 锚点同步升级（但 patch 仍不补写 lot_id 本身）

    Phase 4A-2a:
    - 强化 lot 合法性：lot_id 非空时必须属于 (warehouse_id, item_id)
    """
    # ✅ Step A: final guardrail (do not trust upstream)
    await assert_lot_belongs_to(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        lot_id=lot_id,
    )

    reason_canon = _canon_reason(reason)
    bc_norm = _norm_batch_code(batch_code)

    base_values = dict(
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        batch_code=bc_norm,
        lot_id=lot_id,
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

    # 幂等命中：仅补齐非核心字段（不补 lot_id）
    old_reason_canon = sa.func.nullif(StockLedger.reason_canon, "")
    old_sub_reason = sa.func.nullif(StockLedger.sub_reason, "")
    old_trace_id = sa.func.nullif(StockLedger.trace_id, "")

    if not _need_patch(
        reason_canon=reason_canon,
        sub_reason=sub_reason,
        trace_id=trace_id,
        production_date=production_date,
        expiry_date=expiry_date,
    ):
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
            *_build_patch_where(
                warehouse_id=warehouse_id,
                item_id=item_id,
                batch_code_norm=bc_norm,
                lot_id=lot_id,
                reason=reason,
                ref=ref,
                ref_line=ref_line,
            )
        )
        .values(**upd_values)
    )

    return 0
