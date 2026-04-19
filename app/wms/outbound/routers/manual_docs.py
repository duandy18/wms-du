# app/wms/outbound/routers/manual_docs.py
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.user.deps.auth import get_current_user
from app.wms.outbound.contracts.manual_doc import (
    ManualOutboundDocCreateIn,
    ManualOutboundDocOut,
)
from app.wms.outbound.repos.manual_doc_repo import (
    create_manual_doc,
    get_manual_doc_head,
    get_manual_doc_lines,
    list_manual_docs,
    release_manual_doc,
    void_manual_doc,
)

router = APIRouter(prefix="/wms/outbound", tags=["wms-outbound-manual-docs"])


async def _build_doc_out(session: AsyncSession, *, doc_id: int) -> ManualOutboundDocOut:
    head = await get_manual_doc_head(session, doc_id=int(doc_id))
    lines = await get_manual_doc_lines(session, doc_id=int(doc_id))
    return ManualOutboundDocOut(
        **head,
        lines=lines,
    )


@router.post("/manual-docs", response_model=ManualOutboundDocOut)
async def create_manual_outbound_doc(
    payload: ManualOutboundDocCreateIn,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> ManualOutboundDocOut:
    doc_id = await create_manual_doc(
        session,
        warehouse_id=int(payload.warehouse_id),
        doc_type=payload.doc_type,
        recipient_name=payload.recipient_name,
        recipient_type=payload.recipient_type,
        recipient_note=payload.recipient_note,
        remark=payload.remark,
        created_by=getattr(user, "id", None),
        lines=[x.model_dump() for x in payload.lines],
    )
    await session.commit()
    return await _build_doc_out(session, doc_id=int(doc_id))


@router.get("/manual-docs", response_model=List[ManualOutboundDocOut])
async def list_manual_outbound_docs(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> List[ManualOutboundDocOut]:
    rows = await list_manual_docs(session, limit=int(limit), offset=int(offset))
    return [ManualOutboundDocOut(**r, lines=[]) for r in rows]


@router.get("/manual-docs/{doc_id}", response_model=ManualOutboundDocOut)
async def get_manual_outbound_doc(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> ManualOutboundDocOut:
    return await _build_doc_out(session, doc_id=int(doc_id))


@router.post("/manual-docs/{doc_id}/release", response_model=ManualOutboundDocOut)
async def release_manual_outbound_doc(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> ManualOutboundDocOut:
    await release_manual_doc(
        session,
        doc_id=int(doc_id),
        released_by=getattr(user, "id", None),
    )
    await session.commit()
    return await _build_doc_out(session, doc_id=int(doc_id))


@router.post("/manual-docs/{doc_id}/void", response_model=ManualOutboundDocOut)
async def void_manual_outbound_doc(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> ManualOutboundDocOut:
    await void_manual_doc(
        session,
        doc_id=int(doc_id),
        voided_by=getattr(user, "id", None),
    )
    await session.commit()
    return await _build_doc_out(session, doc_id=int(doc_id))
