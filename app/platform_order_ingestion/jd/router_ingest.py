# Module split: JD platform order native ingest API routes.
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.platform_order_ingestion.permissions import require_platform_order_ingestion_write
from app.user.deps.auth import get_current_user
from app.platform_order_ingestion.jd.contracts_ingest import (
    JdOrderIngestDataOut,
    JdOrderIngestEnvelopeOut,
    JdOrderIngestRequest,
    JdOrderIngestRowOut,
)
from app.platform_order_ingestion.jd.service_ingest import (
    JdOrderIngestService,
    JdOrderIngestServiceError,
)
from app.platform_order_ingestion.jd.service_real_pull import JdRealPullParams

router = APIRouter(tags=["oms-jd-ingest"])


@router.post(
    "/stores/{store_id}/jd/orders/ingest",
    response_model=JdOrderIngestEnvelopeOut,
    summary="JD 真实拉单入平台原生订单表",
)
async def ingest_store_jd_orders(
    store_id: int,
    payload: JdOrderIngestRequest = Body(default_factory=JdOrderIngestRequest),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> JdOrderIngestEnvelopeOut:
    require_platform_order_ingestion_write(db, current_user)

    try:
        service = JdOrderIngestService()
        result = await service.ingest_order_page(
            session=session,
            params=JdRealPullParams(
                store_id=int(store_id),
                start_time=payload.start_time,
                end_time=payload.end_time,
                page=int(payload.page),
                page_size=int(payload.page_size),
                order_state=payload.order_state,
            ),
        )
        await session.commit()
    except (ValueError, LookupError, JdOrderIngestServiceError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"failed to ingest jd orders: {exc}",
        ) from exc

    return JdOrderIngestEnvelopeOut(
        ok=True,
        data=JdOrderIngestDataOut(
            platform="jd",
            store_id=int(result.store_id),
            store_code=str(result.store_code),
            page=int(result.page),
            page_size=int(result.page_size),
            orders_count=int(result.orders_count),
            success_count=int(result.success_count),
            failed_count=int(result.failed_count),
            has_more=bool(result.has_more),
            start_time=result.start_time,
            end_time=result.end_time,
            rows=[
                JdOrderIngestRowOut(
                    order_id=row.order_id,
                    jd_order_id=row.jd_order_id,
                    status=row.status,
                    error=row.error,
                )
                for row in result.rows
            ],
        ),
    )
