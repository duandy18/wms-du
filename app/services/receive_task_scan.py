# app/services/receive_task_scan.py
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receive_task import ReceiveTaskLine
from app.services.receive_task_query import get_with_lines


async def record_scan(
    session: AsyncSession,
    *,
    task_id: int,
    item_id: int,
    qty: int,
    batch_code: Optional[str] = None,
    production_date: Optional[date] = None,
    expiry_date: Optional[date] = None,
):
    task = await get_with_lines(session, task_id, for_update=True)
    if task.status != "DRAFT":
        raise ValueError(f"任务 {task.id} 状态为 {task.status}，不能再修改")

    target: Optional[ReceiveTaskLine] = None
    for line in task.lines or []:
        if line.item_id == item_id:
            target = line
            break

    if target is None:
        target = ReceiveTaskLine(
            task_id=task.id,
            po_line_id=None,
            item_id=item_id,
            item_name=None,
            item_sku=None,
            category=None,
            spec_text=None,
            base_uom=None,
            purchase_uom=None,
            units_per_case=None,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
            expected_qty=None,
            scanned_qty=0,
            committed_qty=None,
            status="DRAFT",
        )
        session.add(target)
        await session.flush()
    else:
        if batch_code is not None:
            target.batch_code = batch_code
        if production_date is not None:
            target.production_date = production_date
        if expiry_date is not None:
            target.expiry_date = expiry_date

    if qty != 0:
        target.scanned_qty += int(qty)

    if target.expected_qty is not None:
        target.status = "MATCHED" if target.scanned_qty == target.expected_qty else "MISMATCH"
    else:
        target.status = "DRAFT"

    await session.flush()
    return await get_with_lines(session, task.id)
