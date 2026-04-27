# Module split: platform order ingestion store-level status API routes.
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.platform_order_ingestion.contracts_status import (
    PlatformOrderIngestionStoreStatusEnvelopeOut,
)
from app.platform_order_ingestion.services.status import (
    PlatformOrderIngestionStatusService,
    PlatformOrderIngestionStatusServiceError,
    PlatformOrderIngestionStoreNotFoundError,
)

router = APIRouter(tags=["platform-order-ingestion-status"])


@router.get(
    "/stores/{store_id}/platform-order-ingestion/status",
    response_model=PlatformOrderIngestionStoreStatusEnvelopeOut,
    summary="查询店铺平台订单采集状态",
)
async def get_store_platform_order_ingestion_status(
    store_id: int,
    session: AsyncSession = Depends(get_session),
) -> PlatformOrderIngestionStoreStatusEnvelopeOut:
    try:
        service = PlatformOrderIngestionStatusService()
        data = await service.get_store_status(session, store_id=store_id)
    except PlatformOrderIngestionStoreNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlatformOrderIngestionStatusServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PlatformOrderIngestionStoreStatusEnvelopeOut(ok=True, data=data)
