from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.inbound_receipts.contracts.receipt_return_source import InboundReceiptReturnSourceOut
from app.inbound_receipts.repos.inbound_receipt_read_repo import get_inbound_return_source_repo


async def get_inbound_return_source(
    session: AsyncSession,
    *,
    order_key: str,
) -> InboundReceiptReturnSourceOut:
    return await get_inbound_return_source_repo(session, order_key=order_key)
