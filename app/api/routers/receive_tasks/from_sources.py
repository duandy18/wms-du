# app/api/routers/receive_tasks/from_sources.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.receive_task import (
    ReceiveTaskCreateFromOrder,
    ReceiveTaskCreateFromPo,
    ReceiveTaskCreateFromPoSelected,
    ReceiveTaskOut,
)
from app.services.receive_task_service import ReceiveTaskService

svc = ReceiveTaskService()


def register(router: APIRouter) -> None:
    @router.post("/from-po/{po_id}", response_model=ReceiveTaskOut)
    async def create_receive_task_from_po(
        po_id: int,
        payload: ReceiveTaskCreateFromPo,
        session: AsyncSession = Depends(get_session),
    ) -> ReceiveTaskOut:
        try:
            task = await svc.create_for_po(
                session,
                po_id=po_id,
                warehouse_id=payload.warehouse_id,
                include_fully_received=payload.include_fully_received,
            )
            await session.commit()
            return ReceiveTaskOut.model_validate(task)
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/from-po/{po_id}/selected", response_model=ReceiveTaskOut)
    async def create_receive_task_from_po_selected(
        po_id: int,
        payload: ReceiveTaskCreateFromPoSelected,
        session: AsyncSession = Depends(get_session),
    ) -> ReceiveTaskOut:
        """
        选择式创建收货任务（本次到货批次）：

        - qty_planned 为“最小单位（base units）”
        - 只创建本次到货选择的行
        - 每行 expected_qty = qty_planned（最小单位口径）
        """
        try:
            task = await svc.create_for_po_selected(
                session,
                po_id=po_id,
                warehouse_id=payload.warehouse_id,
                lines=payload.lines,
            )
            await session.commit()
            return ReceiveTaskOut.model_validate(task)
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/from-order/{order_id}", response_model=ReceiveTaskOut)
    async def create_receive_task_from_order(
        order_id: int,
        payload: ReceiveTaskCreateFromOrder,
        session: AsyncSession = Depends(get_session),
    ) -> ReceiveTaskOut:
        try:
            task = await svc.create_for_order(
                session,
                order_id=order_id,
                warehouse_id=payload.warehouse_id,
                lines=payload.lines,
            )
            await session.commit()
            return ReceiveTaskOut.model_validate(task)
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))
