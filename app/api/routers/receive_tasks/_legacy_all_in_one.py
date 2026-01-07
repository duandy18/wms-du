# app/api/routers/receive_tasks.py
from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.receive_task import ReceiveTask
from app.schemas.receive_task import (
    ReceiveTaskCommitIn,
    ReceiveTaskCreateFromOrder,
    ReceiveTaskCreateFromPo,
    ReceiveTaskCreateFromPoSelected,
    ReceiveTaskOut,
    ReceiveTaskScanIn,
)
from app.services.receive_task_loaders import load_item_policy_map
from app.services.receive_task_service import ReceiveTaskService

router = APIRouter(prefix="/receive-tasks", tags=["receive-tasks"])

svc = ReceiveTaskService()


class ReceiveSupplementLineOut(BaseModel):
    """补录清单行"""

    task_id: int
    po_id: Optional[int] = None
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    warehouse_id: int

    item_id: int
    item_name: Optional[str] = None

    scanned_qty: int
    batch_code: Optional[str] = None
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None

    # 返回字段名用后端字段，但前端会映射成中文
    missing_fields: List[str] = []


class ReceiveTaskLineMetaIn(BaseModel):
    """补录写回：只更新批次/日期（不改数量）"""

    batch_code: str | None = None
    production_date: date | None = None
    expiry_date: date | None = None


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
    - 只创建本次到货选择的行
    - 每行 expected_qty = qty_planned
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


@router.get("/supplements", response_model=List[ReceiveSupplementLineOut])
async def list_receive_supplements(
    session: AsyncSession = Depends(get_session),
    warehouse_id: Optional[int] = Query(None),
    source_type: Optional[str] = Query(None, description="PO / ORDER"),
    po_id: Optional[int] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    mode: str = Query("hard", description="hard=阻断项（默认） / soft=建议补录"),
) -> List[ReceiveSupplementLineOut]:
    """
    补录清单（给前端“补录中心/补录抽屉”使用）。

    mode=hard（默认）：
      - 只返回会阻断 commit 的缺失项（与 receive_task_commit.py 规则对齐）。
      - 仅 has_shelf_life=True 时才会阻断：
          * 缺 batch_code -> 阻断
          * 缺 production_date -> 阻断
          * 缺 expiry_date 且无法推算（无 shelf_life 参数）-> 阻断
      - has_shelf_life=False：batch_code 空会在 commit 时自动 NOEXP，不作为阻断项。

    mode=soft：
      - 返回“建议补录”的缺失项（不一定阻断 commit）。
      - scanned_qty > 0：
          * 缺 batch_code -> 建议补
          * has_shelf_life=True：缺 production_date / expiry_date -> 建议补（即使可推算也建议补包装到期日）
    """

    mode_norm = (mode or "hard").strip().lower()
    if mode_norm not in {"hard", "soft"}:
        raise HTTPException(status_code=400, detail="mode must be hard or soft")

    stmt = (
        select(ReceiveTask)
        .options(selectinload(ReceiveTask.lines))
        .order_by(ReceiveTask.id.desc())
        .limit(max(limit, 1))
    )

    if warehouse_id is not None:
        stmt = stmt.where(ReceiveTask.warehouse_id == warehouse_id)

    if source_type and source_type.strip():
        stmt = stmt.where(ReceiveTask.source_type == source_type.strip().upper())

    if po_id is not None:
        stmt = stmt.where(ReceiveTask.po_id == po_id)

    res = await session.execute(stmt)
    tasks = list(res.scalars())

    item_ids: list[int] = sorted(
        {
            int(ln.item_id)
            for t in tasks
            for ln in (t.lines or [])
            if ln.item_id is not None
        }
    )
    policy_map = await load_item_policy_map(session, item_ids) if item_ids else {}

    out: list[ReceiveSupplementLineOut] = []

    for t in tasks:
        for ln in (t.lines or []):
            scanned = int(ln.scanned_qty or 0)
            if scanned <= 0:
                continue

            info = policy_map.get(int(ln.item_id)) or {}
            has_sl = bool(info.get("has_shelf_life") or False)

            missing: list[str] = []

            # ---------------------------
            # soft：建议补录（可执行提示）
            # ---------------------------
            if mode_norm == "soft":
                # 只要已收，缺批次就建议补（无论是否有保质期）
                if not ln.batch_code or not str(ln.batch_code).strip():
                    missing.append("batch_code")

                # 有保质期：建议补齐生产/到期
                if has_sl:
                    if ln.production_date is None:
                        missing.append("production_date")
                    if ln.expiry_date is None:
                        # soft 模式：即便有参数可推算，也建议补齐包装上的到期日
                        missing.append("expiry_date")

            # ---------------------------
            # hard：阻断项（与 commit 对齐）
            # ---------------------------
            else:
                if has_sl:
                    if not ln.batch_code or not str(ln.batch_code).strip():
                        missing.append("batch_code")

                    if ln.production_date is None:
                        missing.append("production_date")

                    if ln.expiry_date is None:
                        sv = info.get("shelf_life_value")
                        su = info.get("shelf_life_unit")
                        if sv is None or su is None or not str(su).strip():
                            missing.append("expiry_date")

            if not missing:
                continue

            out.append(
                ReceiveSupplementLineOut(
                    task_id=t.id,
                    po_id=t.po_id,
                    source_type=t.source_type,
                    source_id=int(t.source_id) if t.source_id is not None else None,
                    warehouse_id=t.warehouse_id,
                    item_id=int(ln.item_id),
                    item_name=ln.item_name,
                    scanned_qty=scanned,
                    batch_code=ln.batch_code,
                    production_date=ln.production_date,
                    expiry_date=ln.expiry_date,
                    missing_fields=missing,
                )
            )

    return out


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
