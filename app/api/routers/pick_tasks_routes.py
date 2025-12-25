# app/api/routers/pick_tasks_routes.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.pick_task import PickTask
from app.services.pick_task_service import PickTaskService

from app.api.routers.pick_tasks_helpers import load_task_with_lines
from app.api.routers.pick_tasks_schemas import (
    PickTaskCommitIn,
    PickTaskCommitResult,
    PickTaskCreateFromOrder,
    PickTaskDiffLineOut,
    PickTaskDiffSummaryOut,
    PickTaskOut,
    PickTaskScanIn,
)


def register(router: APIRouter) -> None:
    @router.post("/from-order/{order_id}", response_model=PickTaskOut)
    async def create_pick_task_from_order(
        order_id: int,
        payload: PickTaskCreateFromOrder,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskOut:
        svc = PickTaskService(session)
        try:
            task = await svc.create_for_order(
                order_id=order_id,
                warehouse_id=payload.warehouse_id,
                source=payload.source,
                priority=payload.priority,
            )
            await session.commit()
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))
        except Exception:
            await session.rollback()
            raise

        return PickTaskOut.model_validate(task)

    @router.get("", response_model=List[PickTaskOut])
    async def list_pick_tasks(
        warehouse_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
        session: AsyncSession = Depends(get_session),
    ) -> List[PickTaskOut]:
        stmt = select(PickTask).options(selectinload(PickTask.lines))

        if warehouse_id is not None:
            stmt = stmt.where(PickTask.warehouse_id == warehouse_id)

        if status is not None:
            stmt = stmt.where(PickTask.status == status)

        stmt = stmt.order_by(PickTask.priority.asc(), PickTask.id.desc()).limit(limit)

        res = await session.execute(stmt)
        tasks = res.scalars().all()

        return [PickTaskOut.model_validate(t) for t in tasks]

    @router.get("/{task_id}", response_model=PickTaskOut)
    async def get_pick_task(
        task_id: int = Path(..., description="拣货任务 ID"),
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskOut:
        task = await load_task_with_lines(session, task_id)
        return PickTaskOut.model_validate(task)

    @router.post("/{task_id}/scan", response_model=PickTaskOut)
    async def record_scan_for_pick_task(
        task_id: int,
        payload: PickTaskScanIn,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskOut:
        svc = PickTaskService(session)
        try:
            task = await svc.record_scan(
                task_id=task_id,
                item_id=payload.item_id,
                qty=payload.qty,
                batch_code=payload.batch_code,
            )
            await session.commit()
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))
        except HTTPException:
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            raise

        return PickTaskOut.model_validate(task)

    @router.get("/{task_id}/diff", response_model=PickTaskDiffSummaryOut)
    async def get_pick_task_diff(
        task_id: int,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskDiffSummaryOut:
        svc = PickTaskService(session)
        try:
            summary = await svc.compute_diff(task_id=task_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

        lines = [
            PickTaskDiffLineOut(
                item_id=line.item_id,
                req_qty=line.req_qty,
                picked_qty=line.picked_qty,
                delta=line.delta,
                status=line.status,
            )
            for line in summary.lines
        ]

        return PickTaskDiffSummaryOut(
            task_id=summary.task_id,
            has_over=summary.has_over,
            has_under=summary.has_under,
            lines=lines,
        )

    @router.post("/{task_id}/commit", response_model=PickTaskCommitResult)
    async def commit_pick_task(
        task_id: int,
        payload: PickTaskCommitIn,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskCommitResult:
        svc = PickTaskService(session)
        try:
            result = await svc.commit_ship(
                task_id=task_id,
                platform=payload.platform,
                shop_id=payload.shop_id,
                trace_id=payload.trace_id,
                allow_diff=payload.allow_diff,
            )
            await session.commit()
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))
        except Exception:
            await session.rollback()
            raise

        return PickTaskCommitResult(**result)
