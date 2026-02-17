# app/api/routers/receive_tasks/base.py
from __future__ import annotations

from typing import List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.batch_code_contract import fetch_item_has_shelf_life_map, validate_batch_code_contract
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
        # ✅ 主线 A：API 合同收紧（422 拦假码）
        has_shelf_life_map = await fetch_item_has_shelf_life_map(session, {int(payload.item_id)})
        if payload.item_id not in has_shelf_life_map:
            raise HTTPException(status_code=422, detail=f"unknown item_id: {payload.item_id}")

        requires_batch = has_shelf_life_map.get(payload.item_id, False) is True
        batch_code = validate_batch_code_contract(requires_batch=requires_batch, batch_code=payload.batch_code)

        try:
            await svc.record_scan(
                session,
                task_id=task_id,
                item_id=payload.item_id,
                qty=payload.qty,
                batch_code=batch_code,
                production_date=payload.production_date,
                expiry_date=payload.expiry_date,
            )
            await session.commit()

            # ✅ commit 后对象可能 expire（async 懒加载会触发 MissingGreenlet）
            task_after = await svc.get_with_lines(session, task_id)
            return ReceiveTaskOut.model_validate(task_after)
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/{task_id}/commit", response_model=ReceiveTaskOut)
    async def commit_receive_task(
        task_id: int,
        payload: ReceiveTaskCommitIn,
        session: AsyncSession = Depends(get_session),
    ) -> ReceiveTaskOut:
        # ✅ 主线 A：提交前再次做合同校验（防止历史脏数据/绕过 scan 入口）
        try:
            task_before = await svc.get_with_lines(session, task_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

        item_ids: Set[int] = {int(ln.item_id) for ln in (task_before.lines or [])}
        has_shelf_life_map = await fetch_item_has_shelf_life_map(session, item_ids)

        missing_items = [str(i) for i in sorted(item_ids) if i not in has_shelf_life_map]
        if missing_items:
            raise HTTPException(status_code=422, detail=f"unknown item_id(s): {', '.join(missing_items)}")

        for ln in (task_before.lines or []):
            requires_batch = has_shelf_life_map.get(int(ln.item_id), False) is True
            try:
                validate_batch_code_contract(requires_batch=requires_batch, batch_code=ln.batch_code)
            except HTTPException as e:
                raise HTTPException(
                    status_code=422,
                    detail=f"receive_task_line invalid (line_id={ln.id}, item_id={ln.item_id}): {e.detail}",
                )

        try:
            await svc.commit(
                session,
                task_id=task_id,
                trace_id=payload.trace_id,
            )
            await session.commit()

            # ✅ commit 后重新加载，避免 MissingGreenlet（updated_at / lines 等字段惰性加载）
            task_after = await svc.get_with_lines(session, task_id)
            return ReceiveTaskOut.model_validate(task_after)
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))
