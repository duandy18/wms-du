# app/services/inbound_receipt_confirm.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, text
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


def _is_required_policy(v: object) -> bool:
    return str(v or "").strip().upper() == "REQUIRED"


def _parse_shelf_life(*, value: int | None, unit: str | None) -> Tuple[int, str] | None:
    if value is None or unit is None:
        return None
    return int(value), str(unit).upper()


def _compute_expiry_from_shelf_life(*, production_date: date, shelf_life: Tuple[int, str]) -> date:
    """
    方案 B：production_date + shelf_life 推导 expiry_date。
    unit：DAY/WEEK/MONTH/YEAR（DB 已约束）
    """
    from datetime import timedelta
    from dateutil.relativedelta import relativedelta

    v, u = shelf_life
    if u == "DAY":
        return production_date + timedelta(days=v)
    if u == "WEEK":
        return production_date + timedelta(days=7 * v)
    if u == "MONTH":
        return production_date + relativedelta(months=v)
    if u == "YEAR":
        return production_date + relativedelta(years=v)
    raise ValueError(f"unsupported shelf_life_unit: {u!r}")


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


async def _load_item(session: AsyncSession, *, item_id: int) -> Item:
    stmt = select(Item).where(Item.id == int(item_id)).limit(1)
    obj = (await session.execute(stmt)).scalars().first()
    if obj is None:
        raise_problem(
            status_code=422,
            error_code="ITEM_NOT_FOUND",
            message="收货行商品不存在，无法确认。",
            context={"item_id": int(item_id)},
            details=[{"type": "item", "reason": "item_not_found", "item_id": int(item_id)}],
        )
    return obj


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

    # ✅ explain：只检查标签层 + 时间层（不检查 lot_id）
    exp = await explain_receipt(session=session, receipt=receipt)
    if not exp.confirmable:
        details = [e.model_dump() for e in exp.blocking_errors]
        _raise_422_confirm_not_allowed(receipt_id=receipt_id, blocking_errors=details)

    ref = str(getattr(receipt, "ref"))
    occurred_at = getattr(receipt, "occurred_at", None) or datetime.now(UTC)
    warehouse_id = int(getattr(receipt, "warehouse_id"))

    # 预加载 item（避免 N+1）
    item_cache: Dict[int, Item] = {}
    item_ids = sorted({int(getattr(rl, "item_id")) for rl in (receipt.lines or [])})
    for iid in item_ids:
        item_cache[iid] = await _load_item(session, item_id=iid)

    # ✅ confirm 阶段生成 lot_id + 推导并固化 expiry_date（方案 B）
    for rl in receipt.lines or []:
        item_id = int(getattr(rl, "item_id"))
        line_no = int(getattr(rl, "line_no", 0) or 0)
        if line_no <= 0:
            _raise_422_confirm_not_allowed(
                receipt_id=receipt_id,
                blocking_errors=[{"type": "line", "reason": "invalid_line_no", "line_no": int(line_no), "item_id": int(item_id)}],
            )

        item_obj = item_cache[item_id]

        lot_source_policy = str(getattr(item_obj, "lot_source_policy") or "INTERNAL_ONLY")
        expiry_policy = str(getattr(item_obj, "expiry_policy") or "NONE")
        derivation_allowed = bool(getattr(item_obj, "derivation_allowed", False))
        shelf_life = _parse_shelf_life(
            value=getattr(item_obj, "shelf_life_value", None),
            unit=getattr(item_obj, "shelf_life_unit", None),
        )

        lot_code = _normalize_lot_code(getattr(rl, "batch_code", None))

        # --- 标签层（只管 lot_code 必填与伪码）---
        if lot_source_policy == "SUPPLIER_ONLY":
            if lot_code is None:
                _raise_422_confirm_not_allowed(
                    receipt_id=receipt_id,
                    blocking_errors=[{"type": "lot_code", "reason": "lot_code_required", "line_no": int(line_no), "item_id": int(item_id)}],
                )
            if _is_pseudo_lot_code(lot_code):
                _raise_422_confirm_not_allowed(
                    receipt_id=receipt_id,
                    blocking_errors=[{"type": "lot_code", "reason": "pseudo_lot_code_forbidden", "lot_code": lot_code, "line_no": int(line_no)}],
                )
        else:
            if _is_pseudo_lot_code(lot_code):
                _raise_422_confirm_not_allowed(
                    receipt_id=receipt_id,
                    blocking_errors=[{"type": "lot_code", "reason": "pseudo_lot_code_forbidden", "lot_code": lot_code, "line_no": int(line_no)}],
                )

        # --- 时间层（方案 B）---
        pd = getattr(rl, "production_date", None)
        ed = getattr(rl, "expiry_date", None)
        final_expiry: date | None = ed

        if _is_required_policy(expiry_policy):
            if ed is None:
                if not derivation_allowed:
                    _raise_422_confirm_not_allowed(
                        receipt_id=receipt_id,
                        blocking_errors=[{"type": "expiry", "reason": "expiry_date_required_derivation_disabled", "line_no": int(line_no), "item_id": int(item_id)}],
                    )
                if pd is None:
                    _raise_422_confirm_not_allowed(
                        receipt_id=receipt_id,
                        blocking_errors=[{"type": "expiry", "reason": "production_date_required_for_derivation", "line_no": int(line_no), "item_id": int(item_id)}],
                    )
                if shelf_life is None:
                    _raise_422_confirm_not_allowed(
                        receipt_id=receipt_id,
                        blocking_errors=[{"type": "expiry", "reason": "shelf_life_not_configured", "line_no": int(line_no), "item_id": int(item_id)}],
                    )

                final_expiry = _compute_expiry_from_shelf_life(production_date=pd, shelf_life=shelf_life)
                rl.expiry_date = final_expiry
        else:
            # NONE：保持干净（强制不允许日期）
            if pd is not None or ed is not None:
                _raise_422_confirm_not_allowed(
                    receipt_id=receipt_id,
                    blocking_errors=[{"type": "expiry", "reason": "dates_must_be_null_for_none_policy", "line_no": int(line_no), "item_id": int(item_id)}],
                )
            rl.production_date = None
            rl.expiry_date = None
            pd = None
            final_expiry = None

        # --- 生成 lot_id（仅在 confirm）---
        if getattr(rl, "lot_id", None) is None:
            if lot_source_policy == "SUPPLIER_ONLY":
                new_lot_id = await resolve_or_create_lot(
                    db=session,
                    warehouse_id=int(warehouse_id),
                    item=item_obj,
                    lot_code_source="SUPPLIER",
                    lot_code=str(lot_code),
                    source_receipt_id=None,
                    source_line_no=None,
                    production_date=pd,
                    expiry_date=final_expiry,
                    expiry_source="EXPLICIT" if ed is not None else None,
                    shelf_life_days_applied=None,
                )
            else:
                new_lot_id = await resolve_or_create_lot(
                    db=session,
                    warehouse_id=int(warehouse_id),
                    item=item_obj,
                    lot_code_source="INTERNAL",
                    lot_code=None,
                    source_receipt_id=int(receipt.id),
                    source_line_no=int(line_no),
                    production_date=pd,
                    expiry_date=final_expiry,
                    expiry_source="EXPLICIT" if ed is not None else None,
                    shelf_life_days_applied=None,
                )
            rl.lot_id = int(new_lot_id)

    stock_svc = StockService()

    base_ref_line = await _load_next_ref_line_base(session, ref=ref, reason=MovementType.INBOUND.value)

    ledger_refs: List[InboundReceiptConfirmLedgerRef] = []

    for idx, rl in enumerate(receipt.lines or [], start=1):
        item_id = int(getattr(rl, "item_id"))
        qty_delta = int(getattr(rl, "qty_received", 0) or 0)
        ref_line = int(base_ref_line + idx)

        line_no = int(getattr(rl, "line_no", 0) or 0)
        lot_id = getattr(rl, "lot_id", None)
        if lot_id is None:
            _raise_422_confirm_not_allowed(
                receipt_id=receipt_id,
                blocking_errors=[{"type": "lot", "reason": "lot_id_required_at_confirm", "line_no": int(line_no), "item_id": int(item_id)}],
            )

        bc = _normalize_lot_code(getattr(rl, "batch_code", None))
        pd = getattr(rl, "production_date", None)
        ed = getattr(rl, "expiry_date", None)

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
            batch_code=bc,  # 展示/追溯字段，不参与身份
            production_date=pd,
            expiry_date=ed,
            trace_id=getattr(receipt, "trace_id", None),
            lot_id=int(lot_id),
        )

        ledger_refs.append(
            InboundReceiptConfirmLedgerRef(
                source_line_key=f"LINE:{line_no}",
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
