# app/oms/platforms/pdd/router_mock.py
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session

from .contracts_mock import (
    PddMockAuthorizeRequest,
    PddMockClearOrdersRequest,
    PddMockIngestOrdersRequest,
)
from .service_mock import PddMockService, PddMockServiceError

router = APIRouter(tags=["oms-pdd-mock"])


@router.post("/pdd/mock/stores/{store_id}/authorize")
async def authorize_pdd_store_mock(
    store_id: int,
    payload: PddMockAuthorizeRequest = Body(default_factory=PddMockAuthorizeRequest),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        service = PddMockService()
        result = await service.mock_authorize_store(
            session=session,
            store_id=store_id,
            granted_identity_display=payload.granted_identity_display,
            access_token=payload.access_token,
            expires_in_days=payload.expires_in_days,
        )
        await session.commit()
    except (ValueError, LookupError, PddMockServiceError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"failed to mock authorize pdd store: {exc}",
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


@router.post("/pdd/mock/stores/{store_id}/orders/ingest")
async def ingest_pdd_orders_mock(
    store_id: int,
    payload: PddMockIngestOrdersRequest = Body(default_factory=PddMockIngestOrdersRequest),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        service = PddMockService()
        result = await service.mock_ingest_orders(
            session=session,
            store_id=store_id,
            scenario=payload.scenario,
            count=payload.count,
        )
        await session.commit()
    except (ValueError, LookupError, PddMockServiceError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"failed to mock ingest pdd orders: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "store_id": result.store_id,
            "scenario": result.scenario,
            "count": result.count,
            "rows": [
                {
                    "order_sn": row.order_sn,
                    "pdd_order_id": row.pdd_order_id,
                    "scenario": row.scenario,
                }
                for row in result.rows
            ],
        },
    }


@router.delete("/pdd/mock/stores/{store_id}/orders")
async def clear_pdd_orders_mock(
    store_id: int,
    payload: PddMockClearOrdersRequest = Body(default_factory=PddMockClearOrdersRequest),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        service = PddMockService()
        result = await service.clear_mock_orders(
            session=session,
            store_id=store_id,
            clear_connection=payload.clear_connection,
            clear_credential=payload.clear_credential,
        )
        await session.commit()
    except (ValueError, PddMockServiceError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"failed to clear pdd mock orders: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "store_id": result.store_id,
            "deleted_orders": result.deleted_orders,
            "deleted_items": result.deleted_items,
            "deleted_connection_rows": result.deleted_connection_rows,
            "deleted_credential_rows": result.deleted_credential_rows,
        },
    }
