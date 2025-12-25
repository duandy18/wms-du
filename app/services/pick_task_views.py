# app/services/pick_task_views.py
from __future__ import annotations

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pick_task_loaders import load_task
from app.services.pick_task_types import PickTaskCommitLine


async def get_commit_lines(
    session: AsyncSession,
    *,
    task_id: int,
    ignore_zero: bool = True,
):
    task = await load_task(session, task_id)
    lines: List[PickTaskCommitLine] = []

    for line in task.lines or []:
        picked = int(line.picked_qty or 0)
        req = int(line.req_qty or 0)
        if ignore_zero and picked <= 0:
            continue

        lines.append(
            PickTaskCommitLine(
                item_id=int(line.item_id),
                req_qty=req,
                picked_qty=picked,
                warehouse_id=int(task.warehouse_id),
                batch_code=(line.batch_code or None),
                order_id=int(line.order_id) if line.order_id is not None else None,
            )
        )

    return task, lines
