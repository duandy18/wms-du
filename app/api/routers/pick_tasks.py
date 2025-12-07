# app/api/routers/pick_tasks.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.pick_task import PickTask
from app.services.pick_task_service import PickTaskService

router = APIRouter(prefix="/pick-tasks", tags=["pick-tasks"])


class PickTaskLineOut(BaseModel):
    id: int
    task_id: int
    order_id: Optional[int]
    order_line_id: Optional[int]
    item_id: int
    req_qty: int
    picked_qty: int
    batch_code: Optional[str]
    status: str
    note: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PickTaskOut(BaseModel):
    id: int
    warehouse_id: int
    ref: Optional[str]
    source: Optional[str]
    priority: int
    status: str
    assigned_to: Optional[str]
    note: Optional[str]
    created_at: datetime
    updated_at: datetime
    lines: List[PickTaskLineOut] = []

    model_config = ConfigDict(from_attributes=True)


class PickTaskCreateFromOrder(BaseModel):
    warehouse_id: Optional[int] = Field(
        None,
        description="拣货仓库 ID；缺省用订单上的 warehouse_id，若为空则 fallback=1",
    )
    source: str = Field(
        "ORDER",
        description="任务来源标记（默认 'ORDER'）",
    )
    priority: int = Field(
        100,
        ge=0,
        description="任务优先级（整数，越小越高，一般 100 即可）",
    )


class PickTaskScanIn(BaseModel):
    item_id: int = Field(..., description="商品 ID")
    qty: int = Field(..., gt=0, description="本次拣货数量（>0）")
    batch_code: Optional[str] = Field(
        None,
        description="批次编码（可选；若为空，后续 commit_ship 会拒绝执行）",
    )


class PickTaskCommitIn(BaseModel):
    platform: str = Field(..., description="平台标识，如 PDD / TAOBAO")
    shop_id: str = Field(..., description="店铺 ID（字符串）")
    trace_id: Optional[str] = Field(
        None,
        description="链路 trace_id，可选；若空则由服务层 fallback 到 ref",
    )
    allow_diff: bool = Field(
        True,
        description="是否允许在存在 OVER/UNDER 的情况下仍然 commit 出库",
    )


class PickTaskDiffLineOut(BaseModel):
    item_id: int
    req_qty: int
    picked_qty: int
    delta: int
    status: str


class PickTaskDiffSummaryOut(BaseModel):
    task_id: int
    has_over: bool
    has_under: bool
    lines: List[PickTaskDiffLineOut]


class PickTaskCommitResult(BaseModel):
    status: str
    task_id: int
    warehouse_id: int
    platform: str
    shop_id: str
    ref: str
    diff: Dict[str, Any]


async def _load_task_with_lines(
    session: AsyncSession,
    task_id: int,
) -> PickTask:
    stmt = select(PickTask).options(selectinload(PickTask.lines)).where(PickTask.id == task_id)
    res = await session.execute(stmt)
    task = res.scalars().first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"PickTask not found: id={task_id}")
    if task.lines:
        task.lines.sort(key=lambda line: (line.id,))
    return task


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
    task = await _load_task_with_lines(session, task_id)
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
