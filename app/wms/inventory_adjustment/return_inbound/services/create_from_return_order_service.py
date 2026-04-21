from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inventory_adjustment.return_inbound.contracts.receipt_create_from_return_order import (
    InboundReceiptCreateFromReturnOrderIn,
    InboundReceiptCreateFromReturnOrderOut,
)
from app.wms.inventory_adjustment.return_inbound.repos.inbound_receipt_write_repo import (
    create_inbound_receipt_from_return_order_repo,
)


async def create_inbound_receipt_from_return_order(
    session: AsyncSession,
    *,
    payload: InboundReceiptCreateFromReturnOrderIn,
    created_by: int | None = None,
) -> InboundReceiptCreateFromReturnOrderOut:
    return await create_inbound_receipt_from_return_order_repo(
        session,
        payload=payload,
        created_by=created_by,
    )
