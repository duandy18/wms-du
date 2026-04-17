from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inbound_operations.contracts.inbound_task_read import (
    InboundTaskReadOut,
)
from app.wms.inbound_operations.repos.inbound_task_read_repo import (
    get_inbound_task_repo,
)


async def get_inbound_task(
    session: AsyncSession,
    *,
    receipt_no: str,
) -> InboundTaskReadOut:
    return await get_inbound_task_repo(session, receipt_no=receipt_no)


__all__ = [
    "get_inbound_task",
]
