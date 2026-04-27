# Module split: Taobao platform order native ingest API routes.
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.platform_order_ingestion.permissions import require_platform_order_ingestion_write
from app.user.deps.auth import get_current_user
from app.platform_order_ingestion.taobao.contracts_ingest import (
    TaobaoOrderIngestDataOut,
    TaobaoOrderIngestEnvelopeOut,
    TaobaoOrderIngestRequest,
    TaobaoOrderIngestRowOut,
)
from app.platform_order_ingestion.taobao.service_ingest import (
    TaobaoOrderIngestService,
    TaobaoOrderIngestServiceError,
)
from app.platform_order_ingestion.taobao.service_real_pull import TaobaoRealPullParams

router = APIRouter(tags=["oms-taobao-ingest"])


@router.post(
    "/stores/{store_id}/taobao/orders/ingest",
    response_model=TaobaoOrderIngestEnvelopeOut,
    summary="淘宝真实拉单入平台原生订单表",
)
async def ingest_store_taobao_orders(
    store_id: int,
    payload: TaobaoOrderIngestRequest = Body(default_factory=TaobaoOrderIngestRequest),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> TaobaoOrderIngestEnvelopeOut:
    require_platform_order_ingestion_write(db, current_user)

    try:
        service = TaobaoOrderIngestService()
        result = await service.ingest_order_page(
            session=session,
            params=TaobaoRealPullParams(
                store_id=int(store_id),
                start_time=payload.start_time,
                end_time=payload.end_time,
                status=payload.status,
                page=int(payload.page),
                page_size=int(payload.page_size),
            ),
        )
        await session.commit()
    except (ValueError, LookupError, TaobaoOrderIngestServiceError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"failed to ingest taobao orders: {exc}",
        ) from exc

    return TaobaoOrderIngestEnvelopeOut(
        ok=True,
        data=TaobaoOrderIngestDataOut(
            platform="taobao",
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
                TaobaoOrderIngestRowOut(
                    tid=row.tid,
                    taobao_order_id=row.taobao_order_id,
                    status=row.status,
                    error=row.error,
                )
                for row in result.rows
            ],
        ),
    )
