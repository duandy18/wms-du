from __future__ import annotations

# Legacy shim

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.return_task import ReturnTask
from app.services.stock_service import StockService
from app.services.return_task_service_impl import ReturnTaskServiceImpl


class ReturnTaskService:
    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self._impl = ReturnTaskServiceImpl(stock_svc=stock_svc)

    async def create_for_po(
        self,
        session: AsyncSession,
        *,
        po_id: int,
        warehouse_id: Optional[int] = None,
        include_zero_received: bool = False,
    ) -> ReturnTask:
        return await self._impl.create_for_po(
            session,
            po_id=po_id,
            warehouse_id=warehouse_id,
            include_zero_received=include_zero_received,
        )

    async def get_with_lines(
        self,
        session: AsyncSession,
        task_id: int,
        *,
        for_update: bool = False,
    ) -> ReturnTask:
        return await self._impl.get_with_lines(session, task_id=task_id, for_update=for_update)

    async def record_pick(
        self,
        session: AsyncSession,
        *,
        task_id: int,
        item_id: int,
        qty: int,
        batch_code: Optional[str] = None,
    ) -> ReturnTask:
        return await self._impl.record_pick(
            session,
            task_id=task_id,
            item_id=item_id,
            qty=qty,
            batch_code=batch_code,
        )

    async def commit(
        self,
        session: AsyncSession,
        *,
        task_id: int,
        trace_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> ReturnTask:
        return await self._impl.commit(
            session,
            task_id=task_id,
            trace_id=trace_id,
            occurred_at=occurred_at,
        )


__all__ = ["ReturnTaskService"]
