# app/services/inbound_receipt_confirm.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    # 稳定顺序（与 explain 保持一致的排序习惯）
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
    """
    继承旧合同：ref_line 必须在 (reason, ref) 维度递增。
    使用 MAX(ref_line) 做基数，confirm 内按 idx 递增。
    """
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


async def confirm_receipt(
    *,
    session: AsyncSession,
    receipt_id: int,
    user_id: int | None = None,
) -> InboundReceiptConfirmOut:
    """
    Phase5：Receipt confirm（唯一库存写入口）
    - 单事务：锁 receipt → 校验（复用 explain）→ 归一化 → StockService.adjust 写 ledger → status=CONFIRMED
    - 幂等：已 CONFIRMED 直接返回（ledger_written=0）
    """
    _ = user_id  # 预留：未来写 confirmed_by

    receipt = await _load_receipt_for_update(session, receipt_id)

    status = str(getattr(receipt, "status", "") or "").upper()

    # 幂等：已确认直接返回，不重复写库存
    if status == "CONFIRMED":
        return InboundReceiptConfirmOut(
            receipt=InboundReceiptOut.model_validate(receipt),
            ledger_written=0,
            ledger_refs=[],
        )

    # Phase5：只允许 DRAFT → CONFIRMED
    if status != "DRAFT":
        _raise_409_state(receipt_id=receipt_id, status=status)

    # 复用 explain 校验器 + 归一化（保证口径一致）
    exp = await explain_receipt(session=session, receipt=receipt)
    if not exp.confirmable:
        details = [e.model_dump() for e in exp.blocking_errors]
        _raise_422_confirm_not_allowed(receipt_id=receipt_id, blocking_errors=details)

    stock_svc = StockService()

    ref = str(getattr(receipt, "ref"))
    occurred_at = getattr(receipt, "occurred_at", None) or datetime.now(UTC)
    warehouse_id = int(getattr(receipt, "warehouse_id"))

    normalized = list(exp.normalized_lines_preview)

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
            batch_code=str(n.batch_code),
            production_date=getattr(n, "production_date", None),
            expiry_date=None,  # 当前归一化键未纳入 expiry_date；后续如需增强再做
            trace_id=getattr(receipt, "trace_id", None),
        )

        ledger_refs.append(
            InboundReceiptConfirmLedgerRef(
                source_line_key=str(n.line_key),
                ref=ref,
                ref_line=ref_line,
                item_id=item_id,
                qty_delta=qty_delta,
                idempotent=bool(res.get("idempotent")) if isinstance(res, dict) else None,
                applied=bool(res.get("applied")) if isinstance(res, dict) else None,
            )
        )

    receipt.status = "CONFIRMED"
    await session.flush()

    return InboundReceiptConfirmOut(
        receipt=InboundReceiptOut.model_validate(receipt),
        ledger_written=len(ledger_refs),
        ledger_refs=ledger_refs,
    )
