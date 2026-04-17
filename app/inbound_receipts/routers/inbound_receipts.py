from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.inbound_receipts.contracts.receipt_create_from_purchase import (
    InboundReceiptCreateFromPurchaseIn,
    InboundReceiptCreateFromPurchaseOut,
)
from app.inbound_receipts.contracts.receipt_create_manual import (
    InboundReceiptCreateManualIn,
    InboundReceiptCreateManualOut,
)
from app.inbound_receipts.contracts.receipt_create_from_return_order import (
    InboundReceiptCreateFromReturnOrderIn,
    InboundReceiptCreateFromReturnOrderOut,
)
from app.inbound_receipts.contracts.receipt_return_source import (
    InboundReceiptReturnSourceOut,
)
from app.inbound_receipts.contracts.receipt_read import (
    InboundReceiptListOut,
    InboundReceiptProgressOut,
    InboundReceiptReadOut,
)
from app.inbound_receipts.contracts.receipt_release import (
    InboundReceiptReleaseOut,
)
from app.inbound_receipts.services.create_from_purchase_service import (
    create_inbound_receipt_from_purchase,
)
from app.inbound_receipts.services.create_manual_service import (
    create_inbound_receipt_manual,
)
from app.inbound_receipts.services.create_from_return_order_service import (
    create_inbound_receipt_from_return_order,
)
from app.inbound_receipts.services.return_source_service import (
    get_inbound_return_source,
)
from app.inbound_receipts.services.read_service import (
    get_inbound_receipt,
    get_inbound_receipt_progress,
    list_inbound_receipts,
    release_inbound_receipt,
)

router = APIRouter(prefix="/inbound-receipts", tags=["inbound-receipts"])


@router.post("/from-purchase", response_model=InboundReceiptCreateFromPurchaseOut)
async def create_inbound_receipt_from_purchase_endpoint(
    payload: InboundReceiptCreateFromPurchaseIn,
    session: AsyncSession = Depends(get_session),
) -> InboundReceiptCreateFromPurchaseOut:
    try:
        out = await create_inbound_receipt_from_purchase(
            session,
            payload=payload,
            created_by=None,
        )
        await session.commit()
        return out
    except NotImplementedError as e:
        await session.rollback()
        raise HTTPException(status_code=501, detail=str(e)) from e
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/manual", response_model=InboundReceiptCreateManualOut)
async def create_inbound_receipt_manual_endpoint(
    payload: InboundReceiptCreateManualIn,
    session: AsyncSession = Depends(get_session),
) -> InboundReceiptCreateManualOut:
    try:
        out = await create_inbound_receipt_manual(
            session,
            payload=payload,
            created_by=None,
        )
        await session.commit()
        return out
    except NotImplementedError as e:
        await session.rollback()
        raise HTTPException(status_code=501, detail=str(e)) from e
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/return-source/{order_key}", response_model=InboundReceiptReturnSourceOut)
async def get_inbound_return_source_endpoint(
    order_key: str,
    session: AsyncSession = Depends(get_session),
) -> InboundReceiptReturnSourceOut:
    try:
        return await get_inbound_return_source(session, order_key=order_key)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/from-return-order", response_model=InboundReceiptCreateFromReturnOrderOut)
async def create_inbound_receipt_from_return_order_endpoint(
    payload: InboundReceiptCreateFromReturnOrderIn,
    session: AsyncSession = Depends(get_session),
) -> InboundReceiptCreateFromReturnOrderOut:
    try:
        out = await create_inbound_receipt_from_return_order(
            session,
            payload=payload,
            created_by=None,
        )
        await session.commit()
        return out
    except NotImplementedError as e:
        await session.rollback()
        raise HTTPException(status_code=501, detail=str(e)) from e
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("", response_model=InboundReceiptListOut)
async def list_inbound_receipts_endpoint(
    session: AsyncSession = Depends(get_session),
) -> InboundReceiptListOut:
    try:
        return await list_inbound_receipts(session)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{receipt_id}", response_model=InboundReceiptReadOut)
async def get_inbound_receipt_endpoint(
    receipt_id: int,
    session: AsyncSession = Depends(get_session),
) -> InboundReceiptReadOut:
    try:
        return await get_inbound_receipt(session, receipt_id=receipt_id)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{receipt_id}/release", response_model=InboundReceiptReleaseOut)
async def release_inbound_receipt_endpoint(
    receipt_id: int,
    session: AsyncSession = Depends(get_session),
) -> InboundReceiptReleaseOut:
    try:
        out = await release_inbound_receipt(session, receipt_id=receipt_id)
        await session.commit()
        return out
    except NotImplementedError as e:
        await session.rollback()
        raise HTTPException(status_code=501, detail=str(e)) from e
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{receipt_id}/progress", response_model=InboundReceiptProgressOut)
async def get_inbound_receipt_progress_endpoint(
    receipt_id: int,
    session: AsyncSession = Depends(get_session),
) -> InboundReceiptProgressOut:
    try:
        return await get_inbound_receipt_progress(session, receipt_id=receipt_id)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


__all__ = ["router"]
