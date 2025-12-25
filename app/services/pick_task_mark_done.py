# app/services/pick_task_mark_done.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pick_task_loaders import load_task

UTC = timezone.utc


async def mark_done(
    session: AsyncSession,
    *,
    task_id: int,
    note: Optional[str] = None,
):
    task = await load_task(session, task_id, for_update=True)
    now = datetime.now(UTC)

    task.status = "DONE"
    task.updated_at = now
    if note:
        task.note = (task.note or "") + f"\n{note}"

    for line in task.lines or []:
        line.status = "DONE"
        line.updated_at = now

    await session.flush()
    return task
