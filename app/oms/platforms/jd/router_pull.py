# app/oms/platforms/jd/router_pull.py
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session

from .service_pull import JdPullService, JdPullServiceError

router = APIRouter(tags=["oms-jd-pull"])


@router.post("/stores/{store_id}/jd/test-pull")
async def test_store_jd_pull(
    store_id: int,
    payload: dict | None = Body(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    京东 test-pull（第一版）。

    当前阶段：
    - 先做前置校验与 connection 状态推进
    - 前置校验通过后，真实拉取一页订单摘要
    - 逐单补详情
    - 不执行 OMS ingest
    - 不落事实表
    """
    payload = payload or {}
    start_time = payload.get("start_time")
    end_time = payload.get("end_time")
    order_state = payload.get("order_state")
    page = int(payload.get("page") or 1)
    page_size = int(payload.get("page_size") or 20)

    try:
        service = JdPullService()
        result = await service.check_pull_ready(
            session=session,
            store_id=store_id,
            start_time=start_time,
            end_time=end_time,
            page=page,
            page_size=page_size,
            order_state=order_state,
        )
        await session.commit()
    except (ValueError, JdPullServiceError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"failed to run jd test-pull: {exc}",
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
            "detailed_orders_count": result.detailed_orders_count,
            "page": result.page,
            "page_size": result.page_size,
            "has_more": result.has_more,
            "start_time": result.start_time,
            "end_time": result.end_time,
            "orders": [
                {
                    "platform_order_id": order.platform_order_id,
                    "order_state": order.order_state,
                    "order_type": order.order_type,
                    "order_start_time": order.order_start_time,
                    "modified": order.modified,
                    "consignee_name_masked": order.consignee_name_masked,
                    "consignee_mobile_masked": order.consignee_mobile_masked,
                    "consignee_address_summary_masked": order.consignee_address_summary_masked,
                    "order_remark": order.order_remark,
                    "order_total_price": order.order_total_price,
                    "items_count": order.items_count,
                    "detail_loaded": order.detail_loaded,
                    "detail": {
                        "order_id": order.detail.order_id,
                        "vender_id": order.detail.vender_id,
                        "order_type": order.detail.order_type,
                        "order_state": order.detail.order_state,
                        "buyer_pin": order.detail.buyer_pin,
                        "consignee_name": order.detail.consignee_name,
                        "consignee_mobile": order.detail.consignee_mobile,
                        "consignee_phone": order.detail.consignee_phone,
                        "consignee_province": order.detail.consignee_province,
                        "consignee_city": order.detail.consignee_city,
                        "consignee_county": order.detail.consignee_county,
                        "consignee_town": order.detail.consignee_town,
                        "consignee_address": order.detail.consignee_address,
                        "order_remark": order.detail.order_remark,
                        "seller_remark": order.detail.seller_remark,
                        "order_total_price": order.detail.order_total_price,
                        "order_seller_price": order.detail.order_seller_price,
                        "freight_price": order.detail.freight_price,
                        "payment_confirm": order.detail.payment_confirm,
                        "order_start_time": order.detail.order_start_time,
                        "order_end_time": order.detail.order_end_time,
                        "modified": order.detail.modified,
                        "items": [
                            {
                                "sku_id": item.sku_id,
                                "outer_sku_id": item.outer_sku_id,
                                "ware_id": item.ware_id,
                                "item_name": item.item_name,
                                "item_total": item.item_total,
                                "item_price": item.item_price,
                                "sku_name": item.sku_name,
                                "gift_point": item.gift_point,
                                "raw_item": item.raw_item,
                            }
                            for item in (order.detail.items or [])
                        ],
                        "raw_payload": order.detail.raw_payload,
                    }
                    if order.detail is not None
                    else None,
                }
                for order in result.orders
            ],
        },
    }
