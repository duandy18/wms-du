# app/services/receive_task_query.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.receive_task import ReceiveTask


async def get_with_lines(
    session: AsyncSession,
    task_id: int,
    *,
    for_update: bool = False,
) -> ReceiveTask:
    stmt = (
        select(ReceiveTask)
        .options(selectinload(ReceiveTask.lines))
        .where(ReceiveTask.id == task_id)
    )
    if for_update:
        stmt = stmt.with_for_update()

    res = await session.execute(stmt)
    task = res.scalars().first()
    if task is None:
        raise ValueError(f"ReceiveTask not found: id={task_id}")

    if task.lines:
        task.lines.sort(key=lambda line: (line.id,))
    return task
