# app/wms/inbound/routers/inbound_commit.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.wms.inbound.contracts.inbound_commit import InboundCommitIn, InboundCommitOut
from app.wms.inbound.services.inbound_commit_service import commit_inbound

router = APIRouter(prefix="/wms/inbound", tags=["wms-inbound"])


@router.post("/commit", response_model=InboundCommitOut)
async def commit_inbound_endpoint(
    payload: InboundCommitIn,
    session: AsyncSession = Depends(get_session),
) -> InboundCommitOut:
    """
    一层式入库提交入口。

    语义：
    - 不持久化后端 draft
    - 一次提交内完成：解析、校验、换算、lot、事件落库、库存/台账写入
    - 采购单入库、手工入库、退货入库等都统一走这条主链，只通过 source_type/source_ref 区分来源
    """
    try:
        out = await commit_inbound(
            session,
            payload=payload,
            user_id=None,
        )
        await session.commit()
        return out
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e


__all__ = ["router"]
