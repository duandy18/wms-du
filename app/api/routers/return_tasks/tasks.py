# app/api/routers/return_tasks/tasks.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.return_task import ReturnTask
from app.schemas.return_task import (
    ReturnTaskCommitIn,
    ReturnTaskCreateFromOrder,
    ReturnTaskOut,
    ReturnTaskReceiveIn,
)
from app.services.return_task_service import ReturnTaskService

svc = ReturnTaskService()


def register_tasks(router: APIRouter) -> None:
    # -----------------------------
    # Create from order (order_ref)
    # -----------------------------
    @router.post("/from-order/{order_id}", response_model=ReturnTaskOut)
    async def create_return_task_from_order(
        order_id: str,  # order_ref
        payload: ReturnTaskCreateFromOrder,
        session: AsyncSession = Depends(get_session),
    ) -> ReturnTaskOut:
        try:
            task = await svc.create_for_order(
                session,
                order_id=order_id,
                warehouse_id=payload.warehouse_id,
                include_zero_shipped=payload.include_zero_shipped,
            )
            await session.commit()
            return ReturnTaskOut.model_validate(task)
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    # -----------------------------
    # List / Get
    # -----------------------------
    @router.get("/", response_model=List[ReturnTaskOut])
    async def list_return_tasks(
        session: AsyncSession = Depends(get_session),
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
        status: Optional[str] = Query(None),
        order_id: Optional[str] = Query(None),
        warehouse_id: Optional[int] = Query(None),
    ) -> List[ReturnTaskOut]:
        stmt = (
            select(ReturnTask)
            .options(selectinload(ReturnTask.lines))
            .order_by(ReturnTask.id.desc())
            .offset(max(skip, 0))
            .limit(max(limit, 1))
        )

        if status:
            stmt = stmt.where(ReturnTask.status == status.strip().upper())
        if order_id is not None:
            stmt = stmt.where(ReturnTask.order_id == str(order_id))
        if warehouse_id is not None:
            stmt = stmt.where(ReturnTask.warehouse_id == warehouse_id)

        res = await session.execute(stmt)
        tasks = list(res.scalars())
        for task in tasks:
            if task.lines:
                task.lines.sort(key=lambda line: (line.id,))

        return [ReturnTaskOut.model_validate(task) for task in tasks]

    @router.get("/{task_id}", response_model=ReturnTaskOut)
    async def get_return_task(
        task_id: int,
        session: AsyncSession = Depends(get_session),
    ) -> ReturnTaskOut:
        try:
            task = await svc.get_with_lines(session, task_id)
            return ReturnTaskOut.model_validate(task)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # =========================================================
    # Receive（新语义入口）
    # =========================================================
    @router.post("/{task_id}/receive", response_model=ReturnTaskOut)
    async def receive_return_task(
        task_id: int,
        payload: ReturnTaskReceiveIn,
        session: AsyncSession = Depends(get_session),
    ) -> ReturnTaskOut:
        try:
            task = await svc.record_receive(
                session,
                task_id=task_id,
                item_id=payload.item_id,
                qty=payload.qty,
            )
            await session.commit()
            return ReturnTaskOut.model_validate(task)
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    # =========================================================
    # Pick（旧路径兼容，内部转发到 receive）
    # =========================================================
    @router.post("/{task_id}/pick", response_model=ReturnTaskOut)
    async def pick_return_task_compat(
        task_id: int,
        payload: ReturnTaskReceiveIn,
        session: AsyncSession = Depends(get_session),
    ) -> ReturnTaskOut:
        return await receive_return_task(task_id, payload, session)

    # -----------------------------
    # Commit
    # -----------------------------
    @router.post("/{task_id}/commit", response_model=ReturnTaskOut)
    async def commit_return_task(
        task_id: int,
        payload: ReturnTaskCommitIn,
        session: AsyncSession = Depends(get_session),
    ) -> ReturnTaskOut:
        try:
            task = await svc.commit(
                session,
                task_id=task_id,
                trace_id=payload.trace_id,
            )
            await session.commit()
            return ReturnTaskOut.model_validate(task)
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))
