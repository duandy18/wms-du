# app/services/receive/receive_po_line.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_receipt import InboundReceiptLine
from app.models.item import Item
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.services.purchase_order_queries import get_po_with_lines
from app.services.qty_base import ordered_base as _ordered_base_impl
from app.services.receive.batch_semantics import (
    BatchMode,
    batch_mode_from_has_shelf_life,
    enforce_batch_semantics,
    ensure_batch_consistent,
    normalize_batch_code,
)
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


def _build_batch_code(*, po_id: int, po_line_no: int, production_date: Optional[date]) -> Optional[str]:
    """
    Phase 1A（入口语义正确化）：
    - 不再使用 NOEXP / NONE 等伪批次占位
    - 若 production_date 缺失，则返回 None（REQUIRED 场景应显式传 batch_code）
    """
    if production_date is None:
        return None
    return f"BATCH-PO{po_id}-L{po_line_no}-{production_date.isoformat()}"


async def _get_item_batch_mode(session: AsyncSession, *, item_id: int) -> BatchMode:
    """
    Phase 1A：items 当前只有 has_shelf_life。
    映射：
    - has_shelf_life=False -> NONE
    - has_shelf_life=True  -> REQUIRED
    """
    row = await session.execute(select(Item.has_shelf_life).where(Item.id == int(item_id)))
    val = row.scalar_one_or_none()
    return batch_mode_from_has_shelf_life(bool(val))


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
    batch_code: Optional[str] = None,
) -> PurchaseOrder:
    """
    Phase5：对某一行执行“收货录入”（行级）。
    - ✅ 只写 Receipt(DRAFT) 事实（InboundReceiptLine）
    - ❌ 不写 stock_ledger / stocks（库存动作只能由 Receipt(CONFIRMED) 触发）
    - qty 为最小单位（base）
    """
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
        raise ValueError(f"在采购单 {po_id} 中未找到匹配的行 (line_id={line_id}, line_no={line_no})")

    draft = await get_latest_po_draft_receipt(session, po_id=int(po.id))
    if draft is None:
        raise ValueError(f"请先开始收货：未找到 PO 的 DRAFT 收货单 (po_id={po_id})")

    ordered_base = int(_ordered_base(target) or 0)
    if ordered_base <= 0:
        raise ValueError(f"行订购数量非法（base 口径）：ordered_base={ordered_base} (line_id={target.id})")

    confirmed_received_base = await sum_confirmed_received_base(session, po_id=int(po.id), po_line_id=int(target.id))
    draft_received_base = await sum_draft_received_base(session, receipt_id=int(draft.id), po_line_id=int(target.id))

    remaining_base = max(0, ordered_base - confirmed_received_base - draft_received_base)
    if qty > remaining_base:
        raise ValueError(
            f"行收货数量超出剩余数量（base 口径）：ordered_base={ordered_base}, "
            f"confirmed_received_base={confirmed_received_base}, draft_received_base={draft_received_base}, "
            f"remaining_base={remaining_base}, try_receive={qty}"
        )

    next_line_no = await next_receipt_line_no(session, receipt_id=int(draft.id))

    item_id_val = int(getattr(target, "item_id"))
    batch_mode = await _get_item_batch_mode(session, item_id=item_id_val)

    units_per_case = int(getattr(target, "units_per_case", 1) or 1)
    po_line_no_val = int(getattr(target, "line_no", 0) or 0)

    raw_batch_code = normalize_batch_code(batch_code) or _build_batch_code(
        po_id=int(po.id),
        po_line_no=po_line_no_val,
        production_date=production_date,
    )

    try:
        enforced_pd, enforced_ed, enforced_code = enforce_batch_semantics(
            batch_mode=batch_mode,
            production_date=production_date,
            expiry_date=expiry_date,
            batch_code=raw_batch_code,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Phase 1A：仅 REQUIRED 且日期齐全时，才写/对齐 batches canonical
    if (
        batch_mode == "REQUIRED"
        and enforced_code is not None
        and enforced_pd is not None
        and enforced_ed is not None
    ):
        await ensure_batch_consistent(
            session,
            warehouse_id=int(getattr(draft, "warehouse_id")),
            item_id=item_id_val,
            batch_code=str(enforced_code),
            production_date=enforced_pd,
            expiry_date=enforced_ed,
        )

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
        batch_code=enforced_code,
        production_date=enforced_pd,
        expiry_date=enforced_ed,
        qty_received=int(qty),
        units_per_case=int(units_per_case),
        qty_units=int(qty),
        unit_cost=None,
        line_amount=None,
        remark=None,
    )
    session.add(rl)
    await session.flush()

    return po
