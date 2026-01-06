# app/api/routers/receive_tasks/supplement.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.receive_task import ReceiveTask
from app.schemas.receive_task import ReceiveTaskOut
from app.schemas.receive_task_supplement import (
    ReceiveSupplementLineOut,
    ReceiveSupplementSummaryOut,
    ReceiveTaskLineMetaIn,
)
from app.services.receive_task_supplement_service import (
    list_receive_supplements,
    summarize_receive_supplements,
)


def register(router: APIRouter) -> None:
    @router.get("/supplements", response_model=List[ReceiveSupplementLineOut])
    async def api_list_receive_supplements(
        session: AsyncSession = Depends(get_session),
        warehouse_id: Optional[int] = Query(None),
        source_type: Optional[str] = Query(None, description="PO / ORDER"),
        po_id: Optional[int] = Query(None),
        limit: int = Query(200, ge=1, le=500),
        mode: str = Query("hard", description="hard=阻断项（默认） / soft=建议补录"),
    ) -> List[ReceiveSupplementLineOut]:
        try:
            return await list_receive_supplements(
                session,
                warehouse_id=warehouse_id,
                source_type=source_type,
                po_id=po_id,
                limit=limit,
                mode=mode,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/supplements/summary", response_model=ReceiveSupplementSummaryOut)
    async def api_supplements_summary(
        session: AsyncSession = Depends(get_session),
        warehouse_id: Optional[int] = Query(None),
        source_type: Optional[str] = Query(None, description="PO / ORDER"),
        po_id: Optional[int] = Query(None),
        limit: int = Query(200, ge=1, le=500),
        mode: str = Query("hard", description="hard=阻断项（默认） / soft=建议补录"),
    ) -> ReceiveSupplementSummaryOut:
        try:
            return await summarize_receive_supplements(
                session,
                warehouse_id=warehouse_id,
                source_type=source_type,
                po_id=po_id,
                limit=limit,
                mode=mode,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.patch("/{task_id}/lines/{item_id}/meta", response_model=ReceiveTaskOut)
    async def patch_receive_task_line_meta(
        task_id: int,
        item_id: int,
        payload: ReceiveTaskLineMetaIn,
        session: AsyncSession = Depends(get_session),
    ) -> ReceiveTaskOut:
        stmt = (
            select(ReceiveTask)
            .options(selectinload(ReceiveTask.lines))
            .where(ReceiveTask.id == task_id)
            .with_for_update()
        )
        res = await session.execute(stmt)
        task = res.scalars().first()
        if task is None:
            raise HTTPException(status_code=404, detail="ReceiveTask not found")

        if task.status == "COMMITTED":
            raise HTTPException(status_code=400, detail="任务已入库，不能修改批次/日期")

        target = None
        for ln in (task.lines or []):
            if int(ln.item_id) == int(item_id):
                target = ln
                break
        if target is None:
            raise HTTPException(status_code=404, detail="ReceiveTaskLine not found")

        if payload.batch_code is not None:
            bc = str(payload.batch_code).strip()
            target.batch_code = bc or None

        if payload.production_date is not None:
            target.production_date = payload.production_date

        if payload.expiry_date is not None:
            target.expiry_date = payload.expiry_date

        await session.commit()
        return ReceiveTaskOut.model_validate(task)
