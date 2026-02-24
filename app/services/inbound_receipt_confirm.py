# app/services/inbound_receipt_confirm.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.batch_code_contract import normalize_optional_batch_code
from app.api.problem import raise_problem
from app.models.enums import MovementType
from app.models.inbound_receipt import InboundReceipt
from app.schemas.inbound_receipt import InboundReceiptOut
from app.schemas.inbound_receipt_confirm import (
    InboundReceiptConfirmLedgerRef,
    InboundReceiptConfirmOut,
)
from app.services.inbound_receipt_explain import explain_receipt
from app.services.stock_service import StockService

UTC = timezone.utc

_PSEUDO_BATCH_TOKENS = {
    "NOEXP",
    "NONE",
    "NULL_BATCH",
    "__NULL_BATCH__",
}


def _is_pseudo_batch_code(batch_code: Optional[str]) -> bool:
    if batch_code is None:
        return False
    s = str(batch_code).strip()
    if not s:
        return False
    return s.upper() in _PSEUDO_BATCH_TOKENS


async def _load_receipt_for_update(session: AsyncSession, receipt_id: int) -> InboundReceipt:
    stmt = (
        select(InboundReceipt)
        .options(selectinload(InboundReceipt.lines))
        .where(InboundReceipt.id == int(receipt_id))
        .with_for_update()
    )
    obj = (await session.execute(stmt)).scalars().first()
    if obj is None:
        raise ValueError("InboundReceipt not found")

    if obj.lines:
        obj.lines.sort(
            key=lambda x: (int(getattr(x, "line_no", 0) or 0), int(getattr(x, "id", 0) or 0))
        )
    return obj


def _raise_422_confirm_not_allowed(*, receipt_id: int, blocking_errors: list[dict]) -> None:
    raise_problem(
        status_code=422,
        error_code="RECEIPT_NOT_CONFIRMABLE",
        message="收货单不满足确认条件，请先修正后再确认。",
        context={"receipt_id": int(receipt_id)},
        details=blocking_errors,
    )


def _raise_409_state(*, receipt_id: int, status: str) -> None:
    raise_problem(
        status_code=409,
        error_code="RECEIPT_STATE_CONFLICT",
        message="收货单状态冲突，无法确认。",
        context={"receipt_id": int(receipt_id), "status": str(status)},
        details=[{"type": "state", "reason": f"status={status}"}],
    )


async def _load_next_ref_line_base(session: AsyncSession, *, ref: str, reason: str) -> int:
    row = await session.execute(
        text(
            """
            SELECT COALESCE(MAX(ref_line), 0)
              FROM stock_ledger
             WHERE ref = :ref
               AND reason = :reason
            """
        ),
        {"ref": str(ref), "reason": str(reason)},
    )
    return int(row.scalar() or 0)


def _opt_bool(res: object, key: str) -> bool | None:
    if not isinstance(res, dict):
        return None
    if key not in res:
        return None
    return bool(res.get(key))


async def confirm_receipt(
    *,
    session: AsyncSession,
    receipt_id: int,
    user_id: int | None = None,
) -> InboundReceiptConfirmOut:
    _ = user_id

    receipt = await _load_receipt_for_update(session, receipt_id)

    status = str(getattr(receipt, "status", "") or "").upper()

    if status == "CONFIRMED":
        return InboundReceiptConfirmOut(
            receipt=InboundReceiptOut.model_validate(receipt),
            ledger_written=0,
            ledger_refs=[],
        )

    if status != "DRAFT":
        _raise_409_state(receipt_id=receipt_id, status=status)

    exp = await explain_receipt(session=session, receipt=receipt)
    if not exp.confirmable:
        details = [e.model_dump() for e in exp.blocking_errors]
        _raise_422_confirm_not_allowed(receipt_id=receipt_id, blocking_errors=details)

    ref = str(getattr(receipt, "ref"))
    occurred_at = getattr(receipt, "occurred_at", None) or datetime.now(UTC)
    warehouse_id = int(getattr(receipt, "warehouse_id"))

    normalized = list(exp.normalized_lines_preview)

    # === Phase 3 修复点 ===
    # 构建 line_no -> lot_id 映射（实体来源）
    line_lot_map = {}
    for rl in receipt.lines or []:
        ln = int(getattr(rl, "line_no", 0) or 0)
        if ln not in line_lot_map:
            line_lot_map[ln] = rl.lot_id

    extra_blocking_errors: list[dict] = []
    for n in normalized:
        bc = normalize_optional_batch_code(getattr(n, "batch_code", None))
        pd = getattr(n, "production_date", None)
        ed = getattr(n, "expiry_date", None)

        if _is_pseudo_batch_code(bc):
            extra_blocking_errors.append(
                {
                    "type": "batch",
                    "reason": "pseudo_batch_code_forbidden",
                    "line_key": str(getattr(n, "line_key", "")),
                    "batch_code": bc,
                }
            )

        if bc is None and (pd is not None or ed is not None):
            extra_blocking_errors.append(
                {
                    "type": "batch",
                    "reason": "none_mode_dates_must_be_null",
                    "line_key": str(getattr(n, "line_key", "")),
                    "production_date": str(pd) if pd else None,
                    "expiry_date": str(ed) if ed else None,
                }
            )

    if extra_blocking_errors:
        _raise_422_confirm_not_allowed(receipt_id=receipt_id, blocking_errors=extra_blocking_errors)

    stock_svc = StockService()

    base_ref_line = await _load_next_ref_line_base(
        session,
        ref=ref,
        reason=MovementType.INBOUND.value,
    )

    ledger_refs: List[InboundReceiptConfirmLedgerRef] = []

    for idx, n in enumerate(normalized, start=1):
        item_id = int(n.item_id)
        qty_delta = int(n.qty_total)
        ref_line = int(base_ref_line + idx)

        bc = normalize_optional_batch_code(getattr(n, "batch_code", None))
        pd = getattr(n, "production_date", None)
        ed = getattr(n, "expiry_date", None)

        if bc is None:
            pd = None
            ed = None

        line_no = int(getattr(n, "line_no", 0) or 0)
        lot_id = line_lot_map.get(line_no)

        res = await stock_svc.adjust(
            session=session,
            item_id=item_id,
            warehouse_id=warehouse_id,
            delta=qty_delta,
            reason=MovementType.INBOUND,
            ref=ref,
            ref_line=ref_line,
            occurred_at=occurred_at,
            meta={"source": "inbound-receipt-confirm", "receipt_id": int(receipt_id)},
            batch_code=bc,
            production_date=pd,
            expiry_date=ed,
            trace_id=getattr(receipt, "trace_id", None),
            lot_id=lot_id,  # ✅ 正确透传
        )

        ledger_refs.append(
            InboundReceiptConfirmLedgerRef(
                source_line_key=str(getattr(n, "line_key", "")),
                ref=ref,
                ref_line=ref_line,
                item_id=item_id,
                qty_delta=qty_delta,
                idempotent=_opt_bool(res, "idempotent"),
                applied=_opt_bool(res, "applied"),
            )
        )

    receipt.status = "CONFIRMED"
    await session.flush()

    return InboundReceiptConfirmOut(
        receipt=InboundReceiptOut.model_validate(receipt),
        ledger_written=len(ledger_refs),
        ledger_refs=ledger_refs,
    )
