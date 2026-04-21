from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inventory_adjustment.return_inbound.contracts.receipt_create_from_purchase import (
    InboundReceiptCreateFromPurchaseIn,
    InboundReceiptCreateFromPurchaseOut,
)
from app.wms.inventory_adjustment.return_inbound.repos.inbound_receipt_write_repo import (
    create_inbound_receipt_from_purchase_repo,
)


async def create_inbound_receipt_from_purchase(
    session: AsyncSession,
    *,
    payload: InboundReceiptCreateFromPurchaseIn,
    created_by: int | None = None,
) -> InboundReceiptCreateFromPurchaseOut:
    return await create_inbound_receipt_from_purchase_repo(
        session,
        payload=payload,
        created_by=created_by,
    )


__all__ = [
    "create_inbound_receipt_from_purchase",
]
