from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.outbound.contracts.lot_candidates import (
    OutboundLotCandidateOut,
    OutboundLotCandidatesOut,
)
from app.wms.outbound.repos.outbound_lot_candidate_repo import (
    query_outbound_lot_candidates,
)


class OutboundLotCandidateService:
    @classmethod
    async def get_candidates(
        cls,
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
    ) -> OutboundLotCandidatesOut:
        rows = await query_outbound_lot_candidates(
            session,
            warehouse_id=int(warehouse_id),
            item_id=int(item_id),
        )
        return OutboundLotCandidatesOut(
            warehouse_id=int(warehouse_id),
            item_id=int(item_id),
            candidates=[OutboundLotCandidateOut(**row) for row in rows],
        )


__all__ = ["OutboundLotCandidateService"]
