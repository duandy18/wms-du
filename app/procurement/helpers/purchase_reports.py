# app/procurement/helpers/purchase_reports.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.pms.public.items.services.item_read_service import ItemReadService
from app.procurement.models.purchase_order import PurchaseOrder
from app.procurement.models.purchase_order_line_completion import PurchaseOrderLineCompletion


TimeMode = str  # "purchase_time" | "last_received"


async def resolve_report_item_ids(
    session: AsyncSession,
    *,
    item_id: Optional[int],
    item_keyword: Optional[str],
) -> Optional[list[int]]:
    """
    返回：
    - [item_id]：显式 item_id 过滤
    - [ids...]：按 PMS public item 搜索出的 item_id 集合
    - None：不加 item 过滤
    """
    if item_id is not None:
        return [int(item_id)]

    kw = str(item_keyword or "").strip()
    if not kw:
        return None

    svc = ItemReadService(session)
    return await svc.asearch_report_item_ids_by_keyword(keyword=kw)


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
    采购报表通用过滤（completion 统一口径）：

    - 统计来源：PurchaseOrderLineCompletion
    - 时间口径（time_mode）：
        * purchase_time（默认）：按 completion.purchase_time 过滤
        * last_received：按 completion.last_received_at 过滤
    - warehouse_id / supplier_id：按 completion 快照字段过滤
    - status：按 PurchaseOrder.status 过滤
    - DRAFT 永远不进采购报表主口径
    """

    normalized_time_mode = str(time_mode or "purchase_time").strip().lower()

    stmt = stmt.where(PurchaseOrder.status != "DRAFT")

    if normalized_time_mode == "last_received":
        if date_from is not None:
            stmt = stmt.where(
                PurchaseOrderLineCompletion.last_received_at
                >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to is not None:
            stmt = stmt.where(
                PurchaseOrderLineCompletion.last_received_at
                <= datetime.combine(date_to, datetime.max.time())
            )
    else:
        if date_from is not None:
            stmt = stmt.where(
                PurchaseOrderLineCompletion.purchase_time
                >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to is not None:
            stmt = stmt.where(
                PurchaseOrderLineCompletion.purchase_time
                <= datetime.combine(date_to, datetime.max.time())
            )

    if warehouse_id is not None:
        stmt = stmt.where(PurchaseOrderLineCompletion.warehouse_id == warehouse_id)

    if supplier_id is not None:
        stmt = stmt.where(PurchaseOrderLineCompletion.supplier_id == supplier_id)

    normalized_status = str(status or "").strip().upper()
    if normalized_status:
        stmt = stmt.where(PurchaseOrder.status == normalized_status)

    return stmt


def time_mode_query(default: str = "purchase_time"):
    """
    统一 Query 定义，避免每个路由散落文案。

    purchase_time: 按采购时间（默认）
    last_received: 按最后收货时间
    """
    return Query(
        default,
        description="时间口径：purchase_time=按采购时间（默认）；last_received=按最后收货时间",
    )
