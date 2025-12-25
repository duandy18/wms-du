# app/api/routers/pick_tasks_helpers.py
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pick_task import PickTask


async def load_task_with_lines(session: AsyncSession, task_id: int) -> PickTask:
    stmt = select(PickTask).options(selectinload(PickTask.lines)).where(PickTask.id == task_id)
    res = await session.execute(stmt)
    task = res.scalars().first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"PickTask not found: id={task_id}")
    if task.lines:
        task.lines.sort(key=lambda line: (line.id,))
    return task
