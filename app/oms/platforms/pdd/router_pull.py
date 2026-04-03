# app/oms/platforms/pdd/router_pull.py
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session

from .service_pull import PddPullService, PddPullServiceError

router = APIRouter(tags=["oms-pdd-pull"])


@router.post("/stores/{store_id}/pdd/test-pull")
async def test_store_pdd_pull(
    store_id: int,
    payload: dict | None = Body(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    拼多多 test-pull（第二版）。

    当前阶段：
    - 先做前置校验与 connection 状态推进
    - 前置校验通过后，真实拉取一页订单摘要
    - 不执行 OMS ingest
    """
    payload = payload or {}
    start_confirm_at = payload.get("start_confirm_at")
    end_confirm_at = payload.get("end_confirm_at")
    page = int(payload.get("page") or 1)
    page_size = int(payload.get("page_size") or 50)

    try:
        service = PddPullService()
        result = await service.check_pull_ready(
            session=session,
            store_id=store_id,
            start_confirm_at=start_confirm_at,
            end_confirm_at=end_confirm_at,
            page=page,
            page_size=page_size,
        )
        await session.commit()
    except (ValueError, PddPullServiceError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"failed to run pdd test-pull: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "platform": result.platform,
            "store_id": result.store_id,
            "auth_source": result.auth_source,
            "connection_status": result.connection_status,
            "credential_status": result.credential_status,
            "reauth_required": result.reauth_required,
            "pull_ready": result.pull_ready,
            "status": result.status,
            "status_reason": result.status_reason,
            "last_authorized_at": result.last_authorized_at,
            "last_pull_checked_at": result.last_pull_checked_at,
            "last_error_at": result.last_error_at,
            "orders_count": result.orders_count,
            "page": result.page,
            "page_size": result.page_size,
            "has_more": result.has_more,
            "start_confirm_at": result.start_confirm_at,
            "end_confirm_at": result.end_confirm_at,
            "orders": [
                {
                    "platform_order_id": order.platform_order_id,
                    "order_status": order.order_status,
                    "confirm_at": order.confirm_at,
                    "receiver_name_masked": order.receiver_name_masked,
                    "receiver_phone_masked": order.receiver_phone_masked,
                    "receiver_address_summary_masked": order.receiver_address_summary_masked,
                    "buyer_memo": order.buyer_memo,
                    "items_count": order.items_count,
                }
                for order in result.orders
            ],
        },
    }
