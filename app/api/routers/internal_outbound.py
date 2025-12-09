# app/api/routers/internal_outbound.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.internal_outbound import InternalOutboundDoc
from app.schemas.internal_outbound import (
    InternalOutboundConfirmIn,
    InternalOutboundCreateDocIn,
    InternalOutboundDocOut,
    InternalOutboundUpsertLineIn,
)
from app.services.internal_outbound_service import InternalOutboundService

router = APIRouter(prefix="/internal-outbound", tags=["internal-outbound"])

svc = InternalOutboundService()


@router.post("/docs", response_model=InternalOutboundDocOut)
async def create_internal_outbound_doc(
    payload: InternalOutboundCreateDocIn,
    session: AsyncSession = Depends(get_session),
) -> InternalOutboundDocOut:
    """
    创建内部出库单（只建头，不带行）：

    - 必须指定 warehouse_id / doc_type / recipient_name；
    - 初始状态为 DRAFT。
    """
    try:
        doc = await svc.create_doc(
            session,
            warehouse_id=payload.warehouse_id,
            doc_type=payload.doc_type,
            recipient_name=payload.recipient_name,
            recipient_type=payload.recipient_type,
            recipient_note=payload.recipient_note,
            note=payload.note,
            created_by=None,  # TODO: 接入 get_current_user 后填 user.id
            trace_id=payload.trace_id,
        )
        await session.commit()
        return InternalOutboundDocOut.model_validate(doc)
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/docs", response_model=List[InternalOutboundDocOut])
async def list_internal_outbound_docs(
    session: AsyncSession = Depends(get_session),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    warehouse_id: Optional[int] = Query(None),
) -> List[InternalOutboundDocOut]:
    """
    列出内部出库单（简单列表）：

    - 可按 status / warehouse_id 过滤；
    - 默认按 id 倒序。
    """
    stmt = (
        select(InternalOutboundDoc)
        .options(selectinload(InternalOutboundDoc.lines))
        .order_by(InternalOutboundDoc.id.desc())
        .offset(max(skip, 0))
        .limit(max(limit, 1))
    )

    if status:
        stmt = stmt.where(InternalOutboundDoc.status == status.strip().upper())
    if warehouse_id is not None:
        stmt = stmt.where(InternalOutboundDoc.warehouse_id == warehouse_id)

    res = await session.execute(stmt)
    docs = list(res.scalars())

    for doc in docs:
        if doc.lines:
            doc.lines.sort(key=lambda ln: (ln.line_no, ln.id))

    return [InternalOutboundDocOut.model_validate(doc) for doc in docs]


@router.get("/docs/{doc_id}", response_model=InternalOutboundDocOut)
async def get_internal_outbound_doc(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
) -> InternalOutboundDocOut:
    """
    获取内部出库单详情（头 + 行）。
    """
    try:
        doc = await svc.get_with_lines(session, doc_id)
        return InternalOutboundDocOut.model_validate(doc)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/docs/{doc_id}/lines", response_model=InternalOutboundDocOut)
async def upsert_internal_outbound_line(
    doc_id: int,
    payload: InternalOutboundUpsertLineIn,
    session: AsyncSession = Depends(get_session),
) -> InternalOutboundDocOut:
    """
    在内部出库单上新增/累加一行：

    - 若存在相同 (item_id, batch_code) 行则累加 requested_qty；
    - 否则新建一行（line_no = 当前最大 + 1）。
    """
    try:
        # 先执行行修改
        await svc.upsert_line(
            session,
            doc_id=doc_id,
            item_id=payload.item_id,
            qty=payload.qty,
            batch_code=payload.batch_code,
            uom=payload.uom,
            note=payload.note,
        )
        await session.commit()

        # 再重新加载一次 doc（确保 lines 完整）
        doc = await svc.get_with_lines(session, doc_id)
        return InternalOutboundDocOut.model_validate(doc)
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/docs/{doc_id}/confirm", response_model=InternalOutboundDocOut)
async def confirm_internal_outbound_doc(
    doc_id: int,
    payload: InternalOutboundConfirmIn,
    session: AsyncSession = Depends(get_session),
) -> InternalOutboundDocOut:
    """
    确认内部出库：

    - 仅 DRAFT 状态可确认；
    - 必须已经填写 recipient_name；
    - 按行扣库存（指定批次或 FEFO），写入 ledger + audit。
    """
    try:
        # TODO：接入 get_current_user 后，将 user.id 传入 user_id
        doc = await svc.confirm(
            session,
            doc_id=doc_id,
            user_id=None,
        )
        await session.commit()
        return InternalOutboundDocOut.model_validate(doc)
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/docs/{doc_id}/cancel", response_model=InternalOutboundDocOut)
async def cancel_internal_outbound_doc(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
) -> InternalOutboundDocOut:
    """
    取消内部出库单：

    - 仅 DRAFT 状态可取消；
    - 不回滚库存（因为还没扣库存），只改状态 + 写审计事件。
    """
    try:
        # TODO：接入 get_current_user 后，将 user.id 传入 user_id
        doc = await svc.cancel(
            session,
            doc_id=doc_id,
            user_id=None,
        )
        await session.commit()
        return InternalOutboundDocOut.model_validate(doc)
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
