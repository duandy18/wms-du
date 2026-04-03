from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.wms.outbound.contracts.outbound_atomic import (
    OutboundAtomicCreateIn,
    OutboundAtomicCreateOut,
)
from app.wms.outbound.services.outbound_atomic_service import create_outbound_atomic

router = APIRouter(prefix="/wms/outbound", tags=["wms-outbound-atomic"])


@router.post("/atomic", response_model=OutboundAtomicCreateOut)
async def create_outbound_atomic_endpoint(
    payload: OutboundAtomicCreateIn,
    session: AsyncSession = Depends(get_session),
) -> OutboundAtomicCreateOut:
    """
    WMS 原子出库入口。

    当前阶段：
    - 仅建立 router/contracts/services 三层骨架
    - service 尚未完成真实扣减逻辑
    """
    return await create_outbound_atomic(session, payload)


__all__ = ["router"]
