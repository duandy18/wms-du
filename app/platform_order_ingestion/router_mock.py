# Module split: platform order ingestion unified mock API routes.
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.platform_order_ingestion.contracts_mock import (
    PlatformOrderIngestionMockAuthorizeRequest,
    PlatformOrderIngestionMockClearOrdersRequest,
    PlatformOrderIngestionMockIngestOrdersRequest,
)
from app.platform_order_ingestion.services.mock_ingestion import (
    PlatformOrderIngestionMockService,
    PlatformOrderIngestionMockServiceError,
)

router = APIRouter(tags=["platform-order-ingestion-mock"])


@router.post("/platform-order-ingestion/mock/stores/{store_id}/authorize")
async def authorize_store_mock(
    store_id: int,
    payload: PlatformOrderIngestionMockAuthorizeRequest = Body(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        service = PlatformOrderIngestionMockService()
        result = await service.mock_authorize_store(
            session=session,
            store_id=store_id,
            platform=payload.platform,
            granted_identity_display=payload.granted_identity_display,
            access_token=payload.access_token,
            refresh_token=payload.refresh_token,
            expires_in_days=payload.expires_in_days,
            pull_ready=payload.pull_ready,
        )
        await session.commit()
    except (ValueError, PlatformOrderIngestionMockServiceError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"failed to mock authorize platform store: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "store_id": result.store_id,
            "platform": result.platform,
            "access_token": result.access_token,
            "expires_at": result.expires_at,
            "connection_status": result.connection_status,
            "credential_status": result.credential_status,
            "pull_ready": result.pull_ready,
            "status": result.status,
            "status_reason": result.status_reason,
        },
    }


@router.post("/platform-order-ingestion/mock/stores/{store_id}/orders/ingest")
async def ingest_store_orders_mock(
    store_id: int,
    payload: PlatformOrderIngestionMockIngestOrdersRequest = Body(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        service = PlatformOrderIngestionMockService()
        result = await service.mock_ingest_orders(
            session=session,
            store_id=store_id,
            platform=payload.platform,
            scenario=payload.scenario,
            count=payload.count,
        )
        await session.commit()
    except (ValueError, PlatformOrderIngestionMockServiceError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"failed to mock ingest platform orders: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "store_id": result.store_id,
            "platform": result.platform,
            "scenario": result.scenario,
            "count": result.count,
            "rows": [
                {
                    "platform_order_no": row.platform_order_no,
                    "native_order_id": row.native_order_id,
                    "scenario": row.scenario,
                }
                for row in result.rows
            ],
        },
    }


@router.delete("/platform-order-ingestion/mock/stores/{store_id}/orders")
async def clear_store_orders_mock(
    store_id: int,
    payload: PlatformOrderIngestionMockClearOrdersRequest = Body(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        service = PlatformOrderIngestionMockService()
        result = await service.clear_mock_orders(
            session=session,
            store_id=store_id,
            platform=payload.platform,
            clear_connection=payload.clear_connection,
            clear_credential=payload.clear_credential,
        )
        await session.commit()
    except (ValueError, PlatformOrderIngestionMockServiceError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"failed to clear platform mock orders: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "store_id": result.store_id,
            "platform": result.platform,
            "deleted_orders": result.deleted_orders,
            "deleted_items": result.deleted_items,
            "deleted_connection_rows": result.deleted_connection_rows,
            "deleted_credential_rows": result.deleted_credential_rows,
        },
    }
