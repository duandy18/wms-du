# app/services/receive_task_create/from_order_return.py
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receive_task import ReceiveTask, ReceiveTaskLine
from app.schemas.receive_task import OrderReturnLineIn
from app.services.receive_task_loaders import (
    load_order_item_qty_map,
    load_order_returned_qty_map,
    load_order_shipped_qty_map,
)
from app.services.receive_task_query import get_with_lines

from .validators import normalize_order_return_lines_base


async def create_for_order(
    session: AsyncSession,
    *,
    order_id: int,
    warehouse_id: Optional[int],
    lines: Sequence[OrderReturnLineIn],
) -> ReceiveTask:
    order_qty_map = await load_order_item_qty_map(session, order_id)
    returned_qty_map = await load_order_returned_qty_map(session, order_id)
    shipped_qty_map = await load_order_shipped_qty_map(session, order_id)

    normalized = normalize_order_return_lines_base(
        order_id=order_id,
        lines=lines,
        order_qty_map=order_qty_map,
        shipped_qty_map=shipped_qty_map,
        returned_qty_map=returned_qty_map,
    )

    wh_id = warehouse_id or 1

    task = ReceiveTask(
        source_type="ORDER",
        source_id=order_id,
        po_id=None,
        supplier_id=None,
        supplier_name=None,
        warehouse_id=wh_id,
        status="DRAFT",
        remark=f"return from ORDER-{order_id}",
    )
    session.add(task)
    await session.flush()

    created_lines: list[ReceiveTaskLine] = []
    for n in normalized:
        created_lines.append(
            ReceiveTaskLine(
                task_id=task.id,
                po_line_id=None,
                item_id=n.item_id,
                item_name=n.item_name,
                item_sku=None,
                category=None,
                spec_text=None,
                base_uom=None,
                purchase_uom=None,
                units_per_case=None,
                batch_code=n.batch_code,
                production_date=None,
                expiry_date=None,
                expected_qty=n.qty_base,  # ✅ base
                scanned_qty=0,
                committed_qty=None,
                status="DRAFT",
            )
        )

    for rtl in created_lines:
        session.add(rtl)

    await session.flush()
    return await get_with_lines(session, task.id)
