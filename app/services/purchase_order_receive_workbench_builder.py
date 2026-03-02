# app/services/purchase_order_receive_workbench_builder.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from app.models.inbound_receipt import InboundReceipt
from app.models.purchase_order import PurchaseOrder
from app.schemas.purchase_order_receive_workbench import (
    PoSummaryOut,
    ReceiptSummaryOut,
    WorkbenchBatchRowOut,
)
from app.services.purchase_order_time import UTC


def ordered_base(line, ordered_base_impl) -> int:
    return int(ordered_base_impl(line) or 0)


def to_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def build_po_summary(po: PurchaseOrder) -> PoSummaryOut:
    return PoSummaryOut(
        po_id=int(po.id),
        warehouse_id=int(getattr(po, "warehouse_id")),
        supplier_id=getattr(po, "supplier_id", None),
        supplier_name=getattr(po, "supplier_name", None),
        status=getattr(po, "status", None),
        occurred_at=getattr(po, "occurred_at", None),
    )


def build_receipt_summary(r: InboundReceipt) -> ReceiptSummaryOut:
    occurred_at = getattr(r, "occurred_at")
    return ReceiptSummaryOut(
        receipt_id=int(r.id),
        ref=str(getattr(r, "ref")),
        status=str(getattr(r, "status")),
        occurred_at=to_utc(occurred_at),
    )


def sort_rows(xs: List[object]) -> None:
    """
    Stable ordering for workbench rows.

    Phase M-5: rows ordering is presentation-only, not a business truth.
    Keep deterministic ordering to avoid UI/test flakiness.
    """
    xs.sort(
        key=lambda x: (
            int(getattr(x, "line_no", 0) or 0),
            int(getattr(x, "po_line_id", 0) or 0),
            int(getattr(x, "item_id", 0) or 0),
        )
    )


def sort_batch_rows(xs: List[WorkbenchBatchRowOut]) -> None:
    xs.sort(
        key=lambda x: (
            int(getattr(x, "lot_id", 0) or 0),
            str(getattr(x, "production_date", "") or ""),
            str(getattr(x, "expiry_date", "") or ""),
        )
    )


def merge_batch_rows(
    *,
    confirmed: List[WorkbenchBatchRowOut],
    draft: List[WorkbenchBatchRowOut],
) -> List[WorkbenchBatchRowOut]:
    merged: Dict[int, Dict[str, object]] = {}

    for b in confirmed:
        lot_id = int(getattr(b, "lot_id", 0) or 0)
        if lot_id not in merged:
            merged[lot_id] = {
                "qty": 0,
                "batch_code": getattr(b, "batch_code", None),
                "production_date": getattr(b, "production_date", None),
                "expiry_date": getattr(b, "expiry_date", None),
            }
        merged[lot_id]["qty"] = int(merged[lot_id]["qty"]) + int(
            getattr(b, "qty_base", 0) or 0
        )

    for b in draft:
        lot_id = int(getattr(b, "lot_id", 0) or 0)
        if lot_id not in merged:
            merged[lot_id] = {
                "qty": 0,
                "batch_code": getattr(b, "batch_code", None),
                "production_date": getattr(b, "production_date", None),
                "expiry_date": getattr(b, "expiry_date", None),
            }
        merged[lot_id]["qty"] = int(merged[lot_id]["qty"]) + int(
            getattr(b, "qty_base", 0) or 0
        )

    out = [
        WorkbenchBatchRowOut(
            lot_id=int(lot_id),
            batch_code=payload.get("batch_code"),
            production_date=payload.get("production_date"),
            expiry_date=payload.get("expiry_date"),
            qty_base=int(payload.get("qty") or 0),
        )
        for lot_id, payload in merged.items()
    ]

    sort_batch_rows(out)
    return out
