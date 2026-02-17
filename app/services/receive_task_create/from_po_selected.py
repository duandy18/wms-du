# app/services/receive_task_create/from_po_selected.py
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receive_task import ReceiveTask, ReceiveTaskLine
from app.schemas.receive_task import ReceiveTaskCreateFromPoSelectedLineIn
from app.services.receive_task_loaders import load_po
from app.services.receive_task_query import get_with_lines

from .validators import normalize_po_selected_lines


async def create_for_po_selected(
    session: AsyncSession,
    *,
    po_id: int,
    warehouse_id: Optional[int] = None,
    lines: Sequence[ReceiveTaskCreateFromPoSelectedLineIn],
) -> ReceiveTask:
    """
    从采购单“选择部分行”创建收货任务（本次到货批次）

    ✅ 口径收敛（最终形态）：
    - qty_planned：最小单位（base units）
    - expected_qty = qty_planned（最小单位）
    - remaining_base = ordered_base - received_base（最小单位）
    """
    # ✅ 合同收敛：对 PO 加锁，避免并发重复创建 DRAFT
    po = await load_po(session, po_id, for_update=True)
    wh_id = warehouse_id or po.warehouse_id

    # ✅ 合同收敛（Phase 2）：PO → ReceiveTask 防重复创建（幂等）
    stmt = (
        select(ReceiveTask.id)
        .where(
            ReceiveTask.source_type == "PO",
            ReceiveTask.po_id == po.id,
            ReceiveTask.warehouse_id == wh_id,
            ReceiveTask.status == "DRAFT",
        )
        .order_by(ReceiveTask.id.desc())
        .limit(1)
    )
    existing_id = (await session.execute(stmt)).scalar_one_or_none()
    if existing_id is not None:
        return await get_with_lines(session, int(existing_id))

    normalized = normalize_po_selected_lines(
        po_id=po.id,
        po_lines=(po.lines or []),
        lines=lines,
    )

    task = ReceiveTask(
        source_type="PO",
        source_id=po.id,
        po_id=po.id,
        supplier_id=po.supplier_id,
        supplier_name=po.supplier_name or po.supplier,
        warehouse_id=wh_id,
        status="DRAFT",
        remark=f"from PO-{po.id} selected",
    )
    session.add(task)
    await session.flush()

    created_lines: list[ReceiveTaskLine] = []
    for n in normalized:
        pol = n.po_line_obj
        qty_planned_base = n.qty_planned_base  # base

        created_lines.append(
            ReceiveTaskLine(
                task_id=task.id,
                po_line_id=int(getattr(pol, "id")),
                item_id=int(getattr(pol, "item_id")),
                item_name=getattr(pol, "item_name", None),
                item_sku=getattr(pol, "item_sku", None),
                category=getattr(pol, "category", None),
                spec_text=getattr(pol, "spec_text", None),
                base_uom=getattr(pol, "base_uom", None),
                purchase_uom=getattr(pol, "purchase_uom", None),
                units_per_case=getattr(pol, "units_per_case", None),
                batch_code=None,
                production_date=None,
                expiry_date=None,
                expected_qty=qty_planned_base,  # ✅ base 口径
                scanned_qty=0,
                committed_qty=None,
                status="DRAFT",
            )
        )

    if not created_lines:
        raise ValueError(f"采购单 {po.id} 未创建任何任务行，无法创建收货任务")

    for rtl in created_lines:
        session.add(rtl)

    await session.flush()
    return await get_with_lines(session, task.id)
