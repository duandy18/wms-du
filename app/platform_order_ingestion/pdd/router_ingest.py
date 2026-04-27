# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.platform_order_ingestion.permissions import require_platform_order_ingestion_write
from app.user.deps.auth import get_current_user
from app.platform_order_ingestion.pdd.contracts_ingest import (
    PddOrderIngestDataOut,
    PddOrderIngestEnvelopeOut,
    PddOrderIngestRequest,
    PddOrderIngestRowOut,
)
from app.platform_order_ingestion.pdd.service_ingest import (
    PddOrderIngestService,
    PddOrderIngestServiceError,
)
from app.platform_order_ingestion.pdd.service_real_pull import PddRealPullParams

router = APIRouter(tags=["oms-pdd-ingest"])


@router.post(
    "/stores/{store_id}/pdd/orders/ingest",
    response_model=PddOrderIngestEnvelopeOut,
    summary="PDD 真实拉单入平台事实表",
)
async def ingest_store_pdd_orders(
    store_id: int,
    payload: PddOrderIngestRequest = Body(default_factory=PddOrderIngestRequest),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PddOrderIngestEnvelopeOut:
    require_platform_order_ingestion_write(db, current_user)

    """
    PDD 真实订单入库入口。

    边界：
    - 拉 PDD 订单摘要页；
    - 逐单补详情并解密；
    - 写入 pdd_orders / pdd_order_items；
    - 不写 platform_order_lines；
    - 不解析 FSKU；
    - 不建内部 orders/order_items；
    - 不写 PDD 内部订单映射表；
    - 不触碰 finance。
    """

    try:
        service = PddOrderIngestService()
        result = await service.ingest_order_page(
            session=session,
            params=PddRealPullParams(
                store_id=int(store_id),
                start_confirm_at=payload.start_confirm_at,
                end_confirm_at=payload.end_confirm_at,
                order_status=int(payload.order_status),
                page=int(payload.page),
                page_size=int(payload.page_size),
            ),
        )
        await session.commit()
    except (ValueError, LookupError, PddOrderIngestServiceError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"failed to ingest pdd orders: {exc}",
        ) from exc

    return PddOrderIngestEnvelopeOut(
        ok=True,
        data=PddOrderIngestDataOut(
            platform="pdd",
            store_id=int(result.store_id),
            store_code=str(result.store_code),
            page=int(result.page),
            page_size=int(result.page_size),
            orders_count=int(result.orders_count),
            success_count=int(result.success_count),
            failed_count=int(result.failed_count),
            has_more=bool(result.has_more),
            start_confirm_at=result.start_confirm_at,
            end_confirm_at=result.end_confirm_at,
            rows=[
                PddOrderIngestRowOut(
                    order_sn=row.order_sn,
                    pdd_order_id=row.pdd_order_id,
                    status=row.status,
                    error=row.error,
                )
                for row in result.rows
            ],
        ),
    )
