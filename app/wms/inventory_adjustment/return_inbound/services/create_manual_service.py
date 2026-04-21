from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inventory_adjustment.return_inbound.contracts.receipt_create_manual import (
    InboundReceiptCreateManualIn,
    InboundReceiptCreateManualOut,
)
from app.wms.inventory_adjustment.return_inbound.repos.inbound_receipt_write_repo import (
    create_inbound_receipt_manual_repo,
)


async def create_inbound_receipt_manual(
    session: AsyncSession,
    *,
    payload: InboundReceiptCreateManualIn,
    created_by: int | None = None,
) -> InboundReceiptCreateManualOut:
    return await create_inbound_receipt_manual_repo(
        session,
        payload=payload,
        created_by=created_by,
    )


__all__ = [
    "create_inbound_receipt_manual",
]
