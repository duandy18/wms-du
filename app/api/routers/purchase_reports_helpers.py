# app/api/routers/purchase_reports_helpers.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from app.models.purchase_order import PurchaseOrder


def apply_common_filters(
    stmt,
    *,
    date_from: Optional[date],
    date_to: Optional[date],
    warehouse_id: Optional[int],
    supplier_id: Optional[int],
    status: Optional[str],
):
    # 时间范围：按采购单创建时间过滤
    if date_from is not None:
        stmt = stmt.where(
            PurchaseOrder.created_at >= datetime.combine(date_from, datetime.min.time())
        )
    if date_to is not None:
        stmt = stmt.where(
            PurchaseOrder.created_at <= datetime.combine(date_to, datetime.max.time())
        )

    if warehouse_id is not None:
        stmt = stmt.where(PurchaseOrder.warehouse_id == warehouse_id)

    if supplier_id is not None:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)

    if status:
        stmt = stmt.where(PurchaseOrder.status == status.strip().upper())

    return stmt
