from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.inbound_receipts.contracts.receipt_read import (
    InboundReceiptListOut,
    InboundReceiptProgressOut,
    InboundReceiptReadOut,
)
from app.inbound_receipts.contracts.receipt_release import (
    InboundReceiptReleaseOut,
)
from app.inbound_receipts.repos.inbound_receipt_read_repo import (
    get_inbound_receipt_progress_repo,
    get_inbound_receipt_repo,
    list_inbound_receipts_repo,
)
from app.inbound_receipts.repos.inbound_receipt_write_repo import (
    release_inbound_receipt_repo,
)


async def list_inbound_receipts(
    session: AsyncSession,
) -> InboundReceiptListOut:
    return await list_inbound_receipts_repo(session)


async def get_inbound_receipt(
    session: AsyncSession,
    *,
    receipt_id: int,
) -> InboundReceiptReadOut:
    return await get_inbound_receipt_repo(session, receipt_id=receipt_id)


async def get_inbound_receipt_progress(
    session: AsyncSession,
    *,
    receipt_id: int,
) -> InboundReceiptProgressOut:
    return await get_inbound_receipt_progress_repo(session, receipt_id=receipt_id)


async def release_inbound_receipt(
    session: AsyncSession,
    *,
    receipt_id: int,
) -> InboundReceiptReleaseOut:
    return await release_inbound_receipt_repo(session, receipt_id=receipt_id)


__all__ = [
    "list_inbound_receipts",
    "get_inbound_receipt",
    "get_inbound_receipt_progress",
    "release_inbound_receipt",
]
