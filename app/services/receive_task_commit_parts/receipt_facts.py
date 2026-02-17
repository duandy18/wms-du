# app/services/receive_task_commit_parts/receipt_facts.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, Tuple

from app.models.inbound_receipt import InboundReceipt, InboundReceiptLine
from app.models.purchase_order_line import PurchaseOrderLine
from app.models.receive_task import ReceiveTask, ReceiveTaskLine
from app.services.receive_task_commit_parts.utils import norm_optional_str


def make_ref(task: ReceiveTask) -> str:
    return (
        f"RT-{task.id}"
        if task.source_type != "ORDER"
        else f"RMA-{int(task.source_id or 0) or task.id}"
    )


def make_sub_reason(task: ReceiveTask) -> str:
    return "RETURN_RECEIPT" if task.source_type == "ORDER" else "PO_RECEIPT"


def ensure_receipt_header(
    *,
    task: ReceiveTask,
    receipt: Optional[InboundReceipt],
    ref: str,
    trace_id: Optional[str],
    now: datetime,
) -> Tuple[Optional[InboundReceipt], bool]:
    if receipt is not None:
        return receipt, False

    supplier_id_val = getattr(task, "supplier_id", None)
    supplier_name_val = getattr(task, "supplier_name", None)

    src_type = str(task.source_type or "PO")
    src_id = (
        int(task.source_id)
        if task.source_id is not None
        else (int(task.po_id) if task.po_id is not None else None)
    )

    receipt = InboundReceipt(
        warehouse_id=int(task.warehouse_id),
        supplier_id=int(supplier_id_val) if supplier_id_val is not None else None,
        supplier_name=str(supplier_name_val) if supplier_name_val else None,
        source_type=src_type,
        source_id=src_id,
        receive_task_id=int(task.id),
        ref=str(ref),
        trace_id=str(trace_id) if trace_id else None,
        status="CONFIRMED",
        remark=str(getattr(task, "remark", "") or ""),
        occurred_at=now,
    )
    return receipt, True


def build_receipt_line(
    *,
    receipt_id: int,
    ref_line: int,
    qty_base: int,
    upc: int,
    task_line: ReceiveTaskLine,
    po_line: Optional[PurchaseOrderLine],
) -> InboundReceiptLine:
    unit_cost: Optional[Decimal] = None
    line_amount: Optional[Decimal] = None

    item_name_snap: Optional[str] = None
    item_sku_snap: Optional[str] = None
    category_snap: Optional[str] = None
    spec_text_snap: Optional[str] = None
    base_uom_snap: Optional[str] = None
    purchase_uom_snap: Optional[str] = None

    po_line_id_val: Optional[int] = None

    if po_line is not None:
        po_line_id_val = int(po_line.id)
        item_name_snap = po_line.item_name
        item_sku_snap = po_line.item_sku
        category_snap = po_line.category
        spec_text_snap = po_line.spec_text
        base_uom_snap = po_line.base_uom
        purchase_uom_snap = po_line.purchase_uom

        if po_line.supply_price is not None:
            unit_cost = Decimal(str(po_line.supply_price))
        if unit_cost is not None:
            line_amount = (Decimal(int(qty_base)) * unit_cost).quantize(Decimal("0.01"))
    else:
        # fallback：task 行快照
        item_name_snap = task_line.item_name
        item_sku_snap = task_line.item_sku
        category_snap = task_line.category
        spec_text_snap = task_line.spec_text
        base_uom_snap = task_line.base_uom
        purchase_uom_snap = task_line.purchase_uom

    # ✅ 事实层 InboundReceiptLine.batch_code NOT NULL：无批次商品用稳定展示值 NOEXP
    receipt_batch_code = norm_optional_str(task_line.batch_code) or "NOEXP"

    return InboundReceiptLine(
        receipt_id=int(receipt_id),
        line_no=int(ref_line),
        po_line_id=po_line_id_val,
        item_id=int(task_line.item_id),
        item_name=item_name_snap or None,
        item_sku=item_sku_snap or None,
        category=category_snap or None,
        spec_text=spec_text_snap or None,
        base_uom=base_uom_snap or None,
        purchase_uom=purchase_uom_snap or None,
        batch_code=receipt_batch_code,
        production_date=task_line.production_date,
        expiry_date=task_line.expiry_date,
        # ✅ qty_received / qty_units 都用 base，允许拆箱/拆件
        qty_received=int(qty_base),
        units_per_case=int(upc),
        qty_units=int(qty_base),
        unit_cost=unit_cost,
        line_amount=line_amount,
        remark=str(task_line.remark or "") if getattr(task_line, "remark", None) else None,
    )
