# app/wms/procurement/services/receive_po_line.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_receipt import InboundReceiptLine
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.wms.procurement.repos.purchase_order_queries_repo import get_po_with_lines
from app.wms.procurement.services.qty_base import ordered_base as _ordered_base_impl
from app.wms.procurement.repos.receive_po_line_repo import (
    load_item_expiry_policy,
    load_item_lot_source_policy,
    require_item_uom_ratio_to_base,
)
from app.wms.procurement.repos.receipt_draft_repo import (
    get_latest_po_draft_receipt,
    next_receipt_line_no,
    sum_confirmed_received_base,
    sum_draft_received_base,
)

_PSEUDO_LOT_CODE_TOKENS = {"NOEXP", "NONE"}


def _ordered_base(line: Any) -> int:
    return _ordered_base_impl(line)


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


def _validate_dates_light(*, production_date: Optional[date], expiry_date: Optional[date]) -> None:
    if production_date is not None and expiry_date is not None and production_date > expiry_date:
        raise ValueError("日期不合法：production_date 不能晚于 expiry_date")


async def receive_po_line(
    session: AsyncSession,
    *,
    po_id: int,
    line_id: Optional[int] = None,
    line_no: Optional[int] = None,
    uom_id: int,
    qty: int,
    occurred_at: Optional[datetime] = None,
    production_date: Optional[date] = None,
    expiry_date: Optional[date] = None,
    barcode: Optional[str] = None,  # 当前不落库：receipt_lines 不承载 barcode；保留签名兼容
    lot_code: Optional[str] = None,  # 作为 lot_code 标签输入（是否必填由 item.lot_source_policy 决定）
) -> PurchaseOrder:
    """
    M-4：收货输入单位合同收敛（硬切）
    - 输入：uom_id + qty（qty 是输入数量，按该 uom）
    - 事实：qty_base = qty * ratio_to_base（ratio 来自 item_uoms）
    - 禁止：units_per_case / 历史字段 fallback
    """
    _ = occurred_at
    _ = barcode

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
            if int(line.id) == int(line_id):
                target = line
                break
    else:
        for line in po.lines:
            if int(line.line_no) == int(line_no):
                target = line
                break

    if target is None:
        raise ValueError(f"在采购单 {po_id} 中未找到匹配的行")

    draft = await get_latest_po_draft_receipt(session, po_id=int(po.id))
    if draft is None:
        raise ValueError(f"请先开始收货：未找到 PO 的 DRAFT 收货单 (po_id={po_id})")

    draft_wh_id = int(getattr(draft, "warehouse_id"))
    po_wh_id = int(getattr(po, "warehouse_id"))
    if draft_wh_id != po_wh_id:
        raise ValueError(f"DRAFT receipt warehouse mismatch: receipt.wh={draft_wh_id} po.wh={po_wh_id}")

    item_id_val = int(getattr(target, "item_id"))

    # ✅ 输入单位合法性：只认 item_uoms
    ratio_to_base, _disp = await require_item_uom_ratio_to_base(session, item_id=item_id_val, uom_id=int(uom_id))
    qty_base = int(qty) * int(ratio_to_base)
    if qty_base <= 0:
        raise ValueError("收货数量换算后 qty_base 必须 > 0")

    ordered_base = int(_ordered_base(target) or 0)
    confirmed_received_base = await sum_confirmed_received_base(session, po_id=int(po.id), po_line_id=int(target.id))
    draft_received_base = await sum_draft_received_base(session, receipt_id=int(draft.id), po_line_id=int(target.id))

    remaining_base = max(0, ordered_base - confirmed_received_base - draft_received_base)
    if qty_base > remaining_base:
        raise ValueError("行收货数量超出剩余数量")

    next_line_no = await next_receipt_line_no(session, receipt_id=int(draft.id))

    expiry_policy = await load_item_expiry_policy(session, item_id=item_id_val)
    if expiry_policy == "NONE":
        production_date = None
        expiry_date = None

    try:
        _validate_dates_light(production_date=production_date, expiry_date=expiry_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    lot_code = _normalize_lot_code(lot_code)
    if _is_pseudo_lot_code(lot_code):
        raise HTTPException(status_code=400, detail="lot_code 禁止伪码（NOEXP/NONE）")

    lot_source_policy = await load_item_lot_source_policy(session, item_id=item_id_val)
    if lot_source_policy == "SUPPLIER_ONLY" and lot_code is None:
        raise HTTPException(status_code=400, detail="供应商 lot_code 必填（lot_source_policy=SUPPLIER_ONLY）")

    # ✅ Route B：draft 不生成 lot_id；confirm 时填
    # ✅ 终态字段：
    # - lot_code_input 作为输入标签/展示码写入 lot_code_input
    # - receipt_status_snapshot NOT NULL（DRAFT/CONFIRMED）
    rl = InboundReceiptLine(
        receipt_id=int(draft.id),
        line_no=int(next_line_no),
        po_line_id=int(getattr(target, "id")),
        item_id=item_id_val,
        warehouse_id=int(draft_wh_id),
        lot_code_input=lot_code,
        production_date=production_date,
        expiry_date=expiry_date,
        uom_id=int(uom_id),
        qty_input=int(qty),
        ratio_to_base_snapshot=int(ratio_to_base),
        qty_base=int(qty_base),
        receipt_status_snapshot="DRAFT",
        remark=None,
        lot_id=None,  # Route B: confirm will fill
    )

    session.add(rl)
    await session.flush()

    return po
