# app/api/routers/receive_tasks/base.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.receive_task import ReceiveTask
from app.schemas.receive_task import ReceiveTaskCommitIn, ReceiveTaskOut, ReceiveTaskScanIn
from app.services.receive_task_service import ReceiveTaskService

svc = ReceiveTaskService()


def register(router: APIRouter) -> None:
    @router.get("/", response_model=List[ReceiveTaskOut])
    async def list_receive_tasks(
        session: AsyncSession = Depends(get_session),
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
        status: Optional[str] = Query(None),
        po_id: Optional[int] = Query(None),
        warehouse_id: Optional[int] = Query(None),
    ) -> List[ReceiveTaskOut]:
        stmt = (
            select(ReceiveTask)
            .options(selectinload(ReceiveTask.lines))
            .order_by(ReceiveTask.id.desc())
            .offset(max(skip, 0))
            .limit(max(limit, 1))
        )

        if status:
            stmt = stmt.where(ReceiveTask.status == status.strip().upper())
        if po_id is not None:
            stmt = stmt.where(ReceiveTask.po_id == po_id)
        if warehouse_id is not None:
            stmt = stmt.where(ReceiveTask.warehouse_id == warehouse_id)

        res = await session.execute(stmt)
        tasks = list(res.scalars())

        for task in tasks:
            if task.lines:
                task.lines.sort(key=lambda line: (line.id,))

        return [ReceiveTaskOut.model_validate(task) for task in tasks]

    @router.get("/{task_id}", response_model=ReceiveTaskOut)
    async def get_receive_task(
        task_id: int,
        session: AsyncSession = Depends(get_session),
    ) -> ReceiveTaskOut:
        try:
            task = await svc.get_with_lines(session, task_id)
            return ReceiveTaskOut.model_validate(task)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/{task_id}/scan", response_model=ReceiveTaskOut)
    async def record_scan_for_task(
        task_id: int,
        payload: ReceiveTaskScanIn,
        session: AsyncSession = Depends(get_session),
    ) -> ReceiveTaskOut:
        try:
            task = await svc.record_scan(
                session,
                task_id=task_id,
                item_id=payload.item_id,
                qty=payload.qty,
                batch_code=payload.batch_code,
                production_date=payload.production_date,
                expiry_date=payload.expiry_date,
            )
            await session.commit()
            return ReceiveTaskOut.model_validate(task)
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/{task_id}/commit", response_model=ReceiveTaskOut)
    async def commit_receive_task(
        task_id: int,
        payload: ReceiveTaskCommitIn,
        session: AsyncSession = Depends(get_session),
    ) -> ReceiveTaskOut:
        try:
            task = await svc.commit(
                session,
                task_id=task_id,
                trace_id=payload.trace_id,
            )
            await session.commit()
            return ReceiveTaskOut.model_validate(task)
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))
