from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.receiving.contracts.inbound_task_read import (
    InboundTaskListOut,
    InboundTaskReadOut,
)
from app.wms.receiving.repos.inbound_task_read_repo import (
    get_inbound_task_repo,
    list_inbound_tasks_repo,
)


async def list_inbound_tasks(session: AsyncSession) -> InboundTaskListOut:
    return await list_inbound_tasks_repo(session)


async def get_inbound_task(
    session: AsyncSession,
    *,
    receipt_no: str,
) -> InboundTaskReadOut:
    return await get_inbound_task_repo(session, receipt_no=receipt_no)


__all__ = [
    "list_inbound_tasks",
    "get_inbound_task",
]
