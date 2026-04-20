from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.user.deps.auth import get_current_user
from app.wms.outbound.contracts.lot_candidates import OutboundLotCandidatesOut
from app.wms.outbound.services.outbound_lot_candidate_service import (
    OutboundLotCandidateService,
)

router = APIRouter(prefix="/wms/outbound", tags=["wms-outbound-lot-candidates"])


@router.get("/lot-candidates", response_model=OutboundLotCandidatesOut)
async def get_outbound_lot_candidates(
    warehouse_id: int = Query(..., ge=1),
    item_id: int = Query(..., ge=1),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> OutboundLotCandidatesOut:
    return await OutboundLotCandidateService.get_candidates(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
    )
