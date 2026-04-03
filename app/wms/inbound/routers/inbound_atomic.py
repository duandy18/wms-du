from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.wms.inbound.contracts.inbound_atomic import (
    InboundAtomicCreateIn,
    InboundAtomicCreateOut,
)
from app.wms.inbound.services.inbound_atomic_service import create_inbound_atomic

router = APIRouter(prefix="/wms/inbound", tags=["wms-inbound-atomic"])


@router.post("/atomic", response_model=InboundAtomicCreateOut)
async def create_inbound_atomic_endpoint(
    payload: InboundAtomicCreateIn,
    session: AsyncSession = Depends(get_session),
) -> InboundAtomicCreateOut:
    """
    WMS 原子入库入口。

    当前阶段：
    - 仅建立 router/contracts/services 三层骨架
    - service 尚未完成真实写入逻辑
    """
    return await create_inbound_atomic(session, payload)


__all__ = ["router"]
