# app/services/receive/receive_po_line.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_receipt import InboundReceiptLine
from app.models.item import Item
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.services.purchase_order_queries import get_po_with_lines
from app.services.qty_base import ordered_base as _ordered_base_impl
from app.services.receive.receipt_draft import (
    get_latest_po_draft_receipt,
    next_receipt_line_no,
    sum_confirmed_received_base,
    sum_draft_received_base,
)


def _ordered_base(line: Any) -> int:
    return _ordered_base_impl(line)


def _normalize_barcode(barcode: Optional[str]) -> Optional[str]:
    if barcode is None:
        return None
    s = str(barcode).strip()
    return s or None


def _normalize_lot_code(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _validate_dates_light(*, production_date: Optional[date], expiry_date: Optional[date]) -> None:
    # DB 也有 ck_inbound_receipt_lines_prod_le_exp，这里给更友好的 400
    if production_date is not None and expiry_date is not None and production_date > expiry_date:
        raise ValueError("日期不合法：production_date 不能晚于 expiry_date")


async def _load_item_expiry_policy(session: AsyncSession, *, item_id: int) -> str:
    row = await session.execute(select(Item.expiry_policy).where(Item.id == int(item_id)))
    v = row.scalar_one_or_none()
    if v is None:
        return "NONE"
    # ✅ Item.expiry_policy 是 ExpiryPolicy Enum：必须用 .value
    return str(getattr(v, "value", v) or "NONE").upper()


async def receive_po_line(
    session: AsyncSession,
    *,
    po_id: int,
    line_id: Optional[int] = None,
    line_no: Optional[int] = None,
    qty: int,
    occurred_at: Optional[datetime] = None,
    production_date: Optional[date] = None,
    expiry_date: Optional[date] = None,
    barcode: Optional[str] = None,
    batch_code: Optional[str] = None,  # 作为 lot_code 标签输入（是否必填由 item.lot_source_policy 决定，交给 explain/confirm）
) -> PurchaseOrder:
    _ = occurred_at

    if qty <= 0:
        raise ValueError("收货数量 qty 必须 > 0")
    if line_id is None and line_no is None:
        raise ValueError("receive_po_line 需要提供 line_id 或 line_no 之一")

    po = await get_po_with_lines(session, po_id, for_update=True)
    if po is None:
        raise ValueError(f"PurchaseOrder not found: id={po_id}")
    if not po.lines:
        raise ValueError(f"采购单 {po_id} 没有任何行，无法执行行级收货")

    target: Optional[PurchaseOrderLine] = None
    if line_id is not None:
        for line in po.lines:
            if line.id == line_id:
                target = line
                break
    else:
        for line in po.lines:
            if line.line_no == line_no:
                target = line
                break

    if target is None:
        raise ValueError(f"在采购单 {po_id} 中未找到匹配的行")

    draft = await get_latest_po_draft_receipt(session, po_id=int(po.id))
    if draft is None:
        raise ValueError(f"请先开始收货：未找到 PO 的 DRAFT 收货单 (po_id={po_id})")

    ordered_base = int(_ordered_base(target) or 0)
    confirmed_received_base = await sum_confirmed_received_base(session, po_id=int(po.id), po_line_id=int(target.id))
    draft_received_base = await sum_draft_received_base(session, receipt_id=int(draft.id), po_line_id=int(target.id))

    remaining_base = max(0, ordered_base - confirmed_received_base - draft_received_base)
    if qty > remaining_base:
        raise ValueError("行收货数量超出剩余数量")

    next_line_no = await next_receipt_line_no(session, receipt_id=int(draft.id))
    item_id_val = int(getattr(target, "item_id"))

    # ✅ 时间层：expiry_policy=NONE 时强制清空日期输入（与 lot_code 去耦合）
    expiry_policy = await _load_item_expiry_policy(session, item_id=item_id_val)
    if expiry_policy == "NONE":
        production_date = None
        expiry_date = None

    try:
        _validate_dates_light(production_date=production_date, expiry_date=expiry_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    rl = InboundReceiptLine(
        receipt_id=int(draft.id),
        line_no=int(next_line_no),
        po_line_id=int(getattr(target, "id")),
        item_id=item_id_val,
        item_name=getattr(target, "item_name", None),
        item_sku=getattr(target, "item_sku", None),
        category=None,
        spec_text=getattr(target, "spec_text", None),
        base_uom=getattr(target, "base_uom", None),
        purchase_uom=getattr(target, "purchase_uom", None),
        barcode=_normalize_barcode(barcode),
        batch_code=_normalize_lot_code(batch_code),
        production_date=production_date,
        expiry_date=expiry_date,
        qty_received=int(qty),
        units_per_case=int(getattr(target, "units_per_case", 1) or 1),
        qty_units=int(qty),
        unit_cost=None,
        line_amount=None,
        remark=None,
        lot_id=None,  # ✅ draft 阶段不产生 lot_id
    )

    session.add(rl)
    await session.flush()

    return po
