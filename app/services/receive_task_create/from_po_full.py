# app/services/receive_task_create/from_po_full.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receive_task import ReceiveTask, ReceiveTaskLine
from app.services.receive_task_loaders import load_po
from app.services.receive_task_query import get_with_lines

from .common import ordered_base_from_line, received_base


async def create_for_po(
    session: AsyncSession,
    *,
    po_id: int,
    warehouse_id: Optional[int] = None,
    include_fully_received: bool = False,
) -> ReceiveTask:
    """
    旧：整单/剩余应收创建（保留备用）

    ✅ 口径收敛（重要）：
    - qty_ordered_base：最小单位订购事实（优先）
    - qty_received：最小单位已收事实
    - expected_qty：最小单位（remaining_base）
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

    task = ReceiveTask(
        source_type="PO",
        source_id=po.id,
        po_id=po.id,
        supplier_id=po.supplier_id,
        supplier_name=po.supplier_name or po.supplier,
        warehouse_id=wh_id,
        status="DRAFT",
        remark=f"from PO-{po.id}",
    )
    session.add(task)
    await session.flush()

    lines_to_create: list[ReceiveTaskLine] = []
    for line in po.lines or []:
        ordered_base = ordered_base_from_line(line)  # base
        rec_base = received_base(getattr(line, "qty_received", None))  # base
        remaining_base = max(ordered_base - rec_base, 0)  # base

        # ✅ base 口径比较（硬规则）
        if remaining_base <= 0 and not include_fully_received:
            continue

        rtl = ReceiveTaskLine(
            task_id=task.id,
            po_line_id=line.id,
            item_id=line.item_id,
            item_name=line.item_name,
            item_sku=line.item_sku,
            category=line.category,
            spec_text=line.spec_text,
            base_uom=line.base_uom,
            purchase_uom=line.purchase_uom,
            units_per_case=line.units_per_case,
            batch_code=None,
            production_date=None,
            expiry_date=None,
            expected_qty=remaining_base,  # ✅ base
            scanned_qty=0,
            committed_qty=None,
            status="DRAFT",
        )
        lines_to_create.append(rtl)

    if not lines_to_create:
        raise ValueError(f"采购单 {po.id} 已无剩余可收数量，无法创建收货任务")

    for rtl in lines_to_create:
        session.add(rtl)

    await session.flush()
    return await get_with_lines(session, task.id)
