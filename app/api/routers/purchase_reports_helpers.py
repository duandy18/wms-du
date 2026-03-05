# app/api/routers/purchase_reports_helpers.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import Query

from app.models.inbound_receipt import InboundReceipt
from app.models.purchase_order import PurchaseOrder


TimeMode = str  # "occurred" | "po_created" | "po_purchase_time"


def apply_common_filters(
    stmt,
    *,
    date_from: Optional[date],
    date_to: Optional[date],
    warehouse_id: Optional[int],
    supplier_id: Optional[int],
    status: Optional[str],
    time_mode: TimeMode,
):
    """
    采购报表通用过滤（Receipt 事实口径）：

    - 统计事实来源：InboundReceipt / InboundReceiptLine
    - 时间维度（time_mode）：
        * occurred（默认）：按 InboundReceipt.occurred_at 过滤
        * po_created：按 PurchaseOrder.created_at 过滤（仅作为维度，不作为统计来源）
        * po_purchase_time：按 PurchaseOrder.purchase_time 过滤（仅作为维度，不作为统计来源）
    - warehouse_id / supplier_id：按 InboundReceipt 字段过滤（事实维度）
    - status：按 PurchaseOrder.status 过滤（仅作为维度；若不关心可不传）
      注意：调用方应当已经 outer join 了 PurchaseOrder（通过 source_type/source_id 的链路），否则 SQL 会无 PurchaseOrder 表引用。
    """

    # 时间范围：默认按收货发生时间（事实时间）
    if time_mode == "occurred":
        if date_from is not None:
            stmt = stmt.where(
                InboundReceipt.occurred_at >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to is not None:
            stmt = stmt.where(
                InboundReceipt.occurred_at <= datetime.combine(date_to, datetime.max.time())
            )

    # 维度时间：按 PO 创建时间 / PO 采购时间切片（统计仍来自 Receipt）
    elif time_mode == "po_created":
        if date_from is not None:
            stmt = stmt.where(
                PurchaseOrder.created_at >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to is not None:
            stmt = stmt.where(
                PurchaseOrder.created_at <= datetime.combine(date_to, datetime.max.time())
            )
    elif time_mode == "po_purchase_time":
        if date_from is not None:
            stmt = stmt.where(
                PurchaseOrder.purchase_time >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to is not None:
            stmt = stmt.where(
                PurchaseOrder.purchase_time <= datetime.combine(date_to, datetime.max.time())
            )
    else:
        # 防御：未知 time_mode 时退回事实时间（不允许报表口径漂移）
        if date_from is not None:
            stmt = stmt.where(
                InboundReceipt.occurred_at >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to is not None:
            stmt = stmt.where(
                InboundReceipt.occurred_at <= datetime.combine(date_to, datetime.max.time())
            )

    if warehouse_id is not None:
        stmt = stmt.where(InboundReceipt.warehouse_id == warehouse_id)

    if supplier_id is not None:
        stmt = stmt.where(InboundReceipt.supplier_id == supplier_id)

    if status:
        stmt = stmt.where(PurchaseOrder.status == status.strip().upper())

    return stmt


def time_mode_query(default: str = "occurred"):
    """
    统一 Query 定义，避免每个路由散落文案。

    occurred: 按收货发生时间（事实时间，默认）
    po_created: 按 PO 创建时间（维度时间）
    po_purchase_time: 按 PO 采购时间（维度时间）
    """
    return Query(
        default,
        description="时间口径：occurred=按收货发生时间（事实，默认）；po_created=按PO创建时间（维度）；po_purchase_time=按PO采购时间（维度）",
    )
