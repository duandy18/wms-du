# app/services/inbound_receipt_confirm.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.problem import raise_problem
from app.models.enums import MovementType
from app.models.inbound_receipt import InboundReceipt
from app.models.item import Item
from app.schemas.inbound_receipt import InboundReceiptOut
from app.schemas.inbound_receipt_confirm import (
    InboundReceiptConfirmLedgerRef,
    InboundReceiptConfirmOut,
)
from app.services.domain.lot_service import resolve_or_create_lot
from app.services.inbound_receipt_explain import explain_receipt
from app.services.stock_service import StockService

UTC = timezone.utc
_PSEUDO_LOT_CODE_TOKENS = {"NOEXP", "NONE"}


def _normalize_lot_code(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _is_pseudo_lot_code(lot_code: Optional[str]) -> bool:
    c = _normalize_lot_code(lot_code)
    if c is None:
        return False
    return c.upper() in _PSEUDO_LOT_CODE_TOKENS


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
        obj.lines.sort(key=lambda x: (int(getattr(x, "line_no", 0) or 0), int(getattr(x, "id", 0) or 0)))
    return obj


async def _load_items_by_ids(session: AsyncSession, item_ids: List[int]) -> Dict[int, Item]:
    if not item_ids:
        return {}
    stmt = select(Item).where(Item.id.in_([int(x) for x in item_ids]))
    rows = (await session.execute(stmt)).scalars().all()
    return {int(x.id): x for x in rows}


def _infer_lot_code_source_from_item(item: Item) -> str:
    """
    Resolve lot_code_source in ('SUPPLIER','INTERNAL') from item.lot_source_policy.

    We intentionally keep mapping conservative:
    - if policy == 'SUPPLIER' => SUPPLIER
    - else => INTERNAL
    """
    v = getattr(item, "lot_source_policy", None)
    s = str(v or "").strip().upper()
    if s == "SUPPLIER":
        return "SUPPLIER"
    if s == "INTERNAL":
        return "INTERNAL"
    # 默认走 INTERNAL（系统内控），避免把未知值当 SUPPLIER 强制批次输入
    return "INTERNAL"


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
        raise_problem(
            status_code=409,
            error_code="RECEIPT_STATE_CONFLICT",
            message="收货单状态冲突，无法确认。",
        )

    exp = await explain_receipt(session=session, receipt=receipt)
    if not exp.confirmable:
        raise_problem(
            status_code=422,
            error_code="RECEIPT_NOT_CONFIRMABLE",
            message="收货单不满足确认条件。",
            details=[e.model_dump() for e in exp.blocking_errors],
        )

    ref = str(getattr(receipt, "ref"))
    occurred_at = getattr(receipt, "occurred_at", None) or datetime.now(UTC)
    warehouse_id = int(getattr(receipt, "warehouse_id"))

    # preload items (avoid N+1)
    item_ids = [int(getattr(rl, "item_id")) for rl in (receipt.lines or [])]
    item_map = await _load_items_by_ids(session, item_ids=item_ids)

    stock_svc = StockService()
    ledger_refs: List[InboundReceiptConfirmLedgerRef] = []

    for idx, rl in enumerate(receipt.lines or [], start=1):
        item_id = int(getattr(rl, "item_id"))
        qty_delta = int(getattr(rl, "qty_base", 0) or 0)

        item = item_map.get(item_id)
        if item is None:
            raise_problem(
                status_code=422,
                error_code="ITEM_NOT_FOUND",
                message=f"商品不存在：item_id={item_id}",
            )

        # A1: DRAFT may have NULL lot_id; CONFIRM must resolve it.
        lot_id = getattr(rl, "lot_id", None)

        if lot_id is None:
            lot_code_source = _infer_lot_code_source_from_item(item)

            # SUPPLIER: lot_code comes from batch_code (legacy field)
            # INTERNAL: identity comes from receipt_id + line_no
            lot_code: Optional[str] = None
            source_receipt_id: Optional[int] = None
            source_line_no: Optional[int] = None

            if lot_code_source == "SUPPLIER":
                lot_code = _normalize_lot_code(getattr(rl, "batch_code", None))
                # keep current behavior: supplier lot_code required, otherwise 422 from lot_service
                # (we do NOT treat pseudo tokens as valid supplier lot codes)
            else:
                source_receipt_id = int(getattr(receipt, "id"))
                source_line_no = int(getattr(rl, "line_no"))

            new_lot_id = await resolve_or_create_lot(
                db=session,
                warehouse_id=warehouse_id,
                item=item,
                lot_code_source=lot_code_source,  # type: ignore[arg-type]
                lot_code=lot_code,
                source_receipt_id=source_receipt_id,
                source_line_no=source_line_no,
            )
            rl.lot_id = int(new_lot_id)
            lot_id = int(new_lot_id)

        # A1: snapshot status on line (DB CHECK uses this)
        if getattr(rl, "receipt_status_snapshot", None) != "CONFIRMED":
            rl.receipt_status_snapshot = "CONFIRMED"

        res = await stock_svc.adjust(
            session=session,
            item_id=item_id,
            warehouse_id=warehouse_id,
            delta=qty_delta,
            reason=MovementType.INBOUND,
            ref=ref,
            ref_line=idx,
            occurred_at=occurred_at,
            batch_code=getattr(rl, "batch_code", None),
            lot_id=int(lot_id),
        )

        ledger_refs.append(
            InboundReceiptConfirmLedgerRef(
                source_line_key=f"LINE:{getattr(rl, 'line_no')}",
                ref=ref,
                ref_line=idx,
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
