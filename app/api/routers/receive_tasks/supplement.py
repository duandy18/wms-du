# app/api/routers/receive_tasks/supplement.py
from __future__ import annotations

from typing import Dict, List, Optional

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


def _normalize_mode(mode: Optional[str]) -> str:
    m = (mode or "hard").strip().lower()
    if m not in {"hard", "soft"}:
        raise ValueError("mode must be hard or soft")
    return m


def _filter_by_task_id(
    rows: List[ReceiveSupplementLineOut], task_id: Optional[int]
) -> List[ReceiveSupplementLineOut]:
    if task_id is None:
        return rows
    tid = int(task_id)
    return [r for r in rows if int(r.task_id) == tid]


def _build_summary(mode_norm: str, rows: List[ReceiveSupplementLineOut]) -> ReceiveSupplementSummaryOut:
    by_field: Dict[str, int] = {}
    for r in rows:
        for f in r.missing_fields or []:
            by_field[f] = by_field.get(f, 0) + 1
    return ReceiveSupplementSummaryOut(
        mode=mode_norm,
        total_rows=len(rows),
        by_field=by_field,
    )


def register(router: APIRouter) -> None:
    @router.get("/supplements", response_model=List[ReceiveSupplementLineOut])
    async def api_list_receive_supplements(
        session: AsyncSession = Depends(get_session),
        warehouse_id: Optional[int] = Query(None),
        source_type: Optional[str] = Query(None, description="PO / ORDER"),
        po_id: Optional[int] = Query(None),
        task_id: Optional[int] = Query(None, description="仅返回指定收货任务的补录清单"),
        limit: int = Query(200, ge=1, le=500),
        mode: str = Query("hard", description="hard=阻断项（默认） / soft=建议补录"),
    ) -> List[ReceiveSupplementLineOut]:
        try:
            # service 仍按原口径（warehouse/source/po/mode/limit）返回；这里做 task_id 的零风险过滤
            rows = await list_receive_supplements(
                session,
                warehouse_id=warehouse_id,
                source_type=source_type,
                po_id=po_id,
                limit=limit,
                mode=mode,
            )
            return _filter_by_task_id(rows, task_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/supplements/summary", response_model=ReceiveSupplementSummaryOut)
    async def api_supplements_summary(
        session: AsyncSession = Depends(get_session),
        warehouse_id: Optional[int] = Query(None),
        source_type: Optional[str] = Query(None, description="PO / ORDER"),
        po_id: Optional[int] = Query(None),
        task_id: Optional[int] = Query(None, description="仅统计指定收货任务的补录汇总"),
        limit: int = Query(200, ge=1, le=500),
        mode: str = Query("hard", description="hard=阻断项（默认） / soft=建议补录"),
    ) -> ReceiveSupplementSummaryOut:
        try:
            # ✅ 无 task_id：保持原行为，直接走 service 的汇总实现
            if task_id is None:
                return await summarize_receive_supplements(
                    session,
                    warehouse_id=warehouse_id,
                    source_type=source_type,
                    po_id=po_id,
                    limit=limit,
                    mode=mode,
                )

            # ✅ 有 task_id：只查一次 list，然后在 router 层做过滤 + 重算 summary
            mode_norm = _normalize_mode(mode)

            rows = await list_receive_supplements(
                session,
                warehouse_id=warehouse_id,
                source_type=source_type,
                po_id=po_id,
                limit=limit,
                mode=mode_norm,
            )
            rows = _filter_by_task_id(rows, task_id)
            return _build_summary(mode_norm, rows)
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
