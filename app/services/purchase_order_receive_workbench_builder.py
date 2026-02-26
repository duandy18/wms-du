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
    """
    Workbench 统一输出 UTC（Z）风格：
    - 若 dt 带 tzinfo：转为 UTC
    - 若 dt 为 naive：按 UTC 解释（避免本地时区漂移）
    """
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


def sort_batch_rows(xs: List[WorkbenchBatchRowOut]) -> None:
    """
    Phase L：workbench rows 排序优先以 lot_id 为稳定主键。
    batch_code 仅展示字段，不再参与 identity/排序主键。
    """
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
    """
    Phase L：
    合并 confirmed + draft，按 lot_id 聚合 qty_received。

    注意：
    - production_date/expiry_date 必须为 canonical（来自 lots），不能用 receipt_line 快照。
    - batch_code 仅作为展示字段，不参与 identity。
    - 无批次商品应 batch_code=None，但 lot_id 必须非空（INTERNAL lot）。
    """
    # lot_id -> payload
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
        merged[lot_id]["qty"] = int(merged[lot_id]["qty"]) + int(getattr(b, "qty_received", 0) or 0)

    for b in draft:
        lot_id = int(getattr(b, "lot_id", 0) or 0)
        if lot_id not in merged:
            merged[lot_id] = {
                "qty": 0,
                "batch_code": getattr(b, "batch_code", None),
                "production_date": getattr(b, "production_date", None),
                "expiry_date": getattr(b, "expiry_date", None),
            }
        merged[lot_id]["qty"] = int(merged[lot_id]["qty"]) + int(getattr(b, "qty_received", 0) or 0)

    out = [
        WorkbenchBatchRowOut(
            lot_id=int(lot_id),  # Phase L：新增字段（schema 需加 Optional[int]）
            batch_code=payload.get("batch_code"),
            production_date=payload.get("production_date"),  # type: ignore[arg-type]
            expiry_date=payload.get("expiry_date"),  # type: ignore[arg-type]
            qty_received=int(payload.get("qty") or 0),
        )
        for lot_id, payload in merged.items()
    ]
    sort_batch_rows(out)
    return out


def sort_rows(rows) -> None:
    rows.sort(key=lambda x: (int(getattr(x, "line_no", 0) or 0), int(getattr(x, "po_line_id", 0) or 0)))
