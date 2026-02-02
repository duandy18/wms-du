# app/api/routers/pick_tasks_routes.py
from __future__ import annotations

from typing import List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.batch_code_contract import fetch_item_has_shelf_life_map, validate_batch_code_contract
from app.api.problem import raise_422
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
        if payload.warehouse_id is None:
            raise_422(
                "warehouse_required",
                "创建拣货任务必须选择仓库。",
                details=[{"type": "validation", "path": "warehouse_id", "reason": "required"}],
            )

        svc = PickTaskService(session)
        try:
            task = await svc.create_for_order(
                order_id=order_id,
                warehouse_id=payload.warehouse_id,
                source=payload.source,
                priority=payload.priority,
            )
            await session.commit()
        except HTTPException:
            await session.rollback()
            raise
        except ValueError as e:
            await session.rollback()
            raise_422("pick_task_create_reject", str(e))
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
        has_shelf_life_map = await fetch_item_has_shelf_life_map(session, {int(payload.item_id)})
        if payload.item_id not in has_shelf_life_map:
            raise_422(
                "unknown_item",
                f"未知商品 item_id={payload.item_id}。",
                details=[{"type": "validation", "path": "item_id", "item_id": int(payload.item_id), "reason": "unknown"}],
            )

        requires_batch = has_shelf_life_map.get(payload.item_id, False) is True
        batch_code = validate_batch_code_contract(requires_batch=requires_batch, batch_code=payload.batch_code)

        svc = PickTaskService(session)
        try:
            task = await svc.record_scan(
                task_id=task_id,
                item_id=payload.item_id,
                qty=payload.qty,
                batch_code=batch_code,
            )
            await session.commit()
        except HTTPException:
            await session.rollback()
            raise
        except ValueError as e:
            await session.rollback()
            raise_422("pick_scan_reject", str(e))
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
            raise_422("pick_task_not_found", str(e))

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
        # 提交前再次做合同校验（防止历史脏数据/绕过 scan 入口）
        task = await load_task_with_lines(session, task_id)
        item_ids: Set[int] = {int(ln.item_id) for ln in (task.lines or [])}
        has_shelf_life_map = await fetch_item_has_shelf_life_map(session, item_ids)

        missing_items = [int(i) for i in sorted(item_ids) if i not in has_shelf_life_map]
        if missing_items:
            raise_422(
                "unknown_item",
                "存在未知商品，禁止提交。",
                details=[
                    {"type": "validation", "path": f"lines[{idx}].item_id", "item_id": int(ln.item_id), "reason": "unknown"}
                    for idx, ln in enumerate(task.lines or [])
                    if int(ln.item_id) in set(missing_items)
                ],
            )

        for idx, ln in enumerate(task.lines or []):
            requires_batch = has_shelf_life_map.get(int(ln.item_id), False) is True
            try:
                validate_batch_code_contract(requires_batch=requires_batch, batch_code=ln.batch_code)
            except HTTPException as e:
                raise_422(
                    "batch_required" if requires_batch else "invalid_batch",
                    "批次信息不合法，禁止提交。",
                    details=[
                        {
                            "type": "batch",
                            "path": f"lines[{idx}]",
                            "item_id": int(ln.item_id),
                            "batch_code": ln.batch_code,
                            "reason": str(e.detail),
                        }
                    ],
                )

        svc = PickTaskService(session)
        try:
            result = await svc.commit_ship(
                task_id=task_id,
                platform=payload.platform,
                shop_id=payload.shop_id,
                handoff_code=payload.handoff_code,
                trace_id=payload.trace_id,
                allow_diff=payload.allow_diff,
            )
            await session.commit()
        except HTTPException:
            await session.rollback()
            raise
        except ValueError as e:
            await session.rollback()
            raise_422(
                "pick_commit_reject",
                str(e),
                details=[{"type": "state", "path": "commit", "reason": str(e)}],
            )
        except Exception:
            await session.rollback()
            raise

        return PickTaskCommitResult(**result)
