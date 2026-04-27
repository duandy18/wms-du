# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/taobao/router_pull.py
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.oms.services.stores_helpers import check_perm
from app.user.deps.auth import get_current_user

from .repository import require_enabled_taobao_app_config
from .service_pull import TaobaoPullOrderResult, TaobaoPullService, TaobaoPullServiceError
from .settings import build_taobao_top_config_from_model


router = APIRouter(tags=["oms-taobao-pull"])


def _detail_out(order: TaobaoPullOrderResult) -> dict | None:
    if order.detail is None:
        return None

    return {
        "tid": order.detail.tid,
        "status": order.detail.status,
        "type": order.detail.type,
        "buyer_nick": order.detail.buyer_nick,
        "buyer_open_uid": order.detail.buyer_open_uid,
        "receiver_name": order.detail.receiver_name,
        "receiver_mobile": order.detail.receiver_mobile,
        "receiver_phone": order.detail.receiver_phone,
        "receiver_state": order.detail.receiver_state,
        "receiver_city": order.detail.receiver_city,
        "receiver_district": order.detail.receiver_district,
        "receiver_town": order.detail.receiver_town,
        "receiver_address": order.detail.receiver_address,
        "receiver_zip": order.detail.receiver_zip,
        "buyer_memo": order.detail.buyer_memo,
        "buyer_message": order.detail.buyer_message,
        "seller_memo": order.detail.seller_memo,
        "seller_flag": order.detail.seller_flag,
        "payment": order.detail.payment,
        "total_fee": order.detail.total_fee,
        "post_fee": order.detail.post_fee,
        "coupon_fee": order.detail.coupon_fee,
        "created": order.detail.created,
        "pay_time": order.detail.pay_time,
        "modified": order.detail.modified,
        "items": [
            {
                "oid": item.oid,
                "num_iid": item.num_iid,
                "sku_id": item.sku_id,
                "outer_iid": item.outer_iid,
                "outer_sku_id": item.outer_sku_id,
                "title": item.title,
                "price": item.price,
                "num": item.num,
                "payment": item.payment,
                "total_fee": item.total_fee,
                "sku_properties_name": item.sku_properties_name,
                "raw_item": item.raw_item,
            }
            for item in (order.detail.items or [])
        ],
        "raw_payload": order.detail.raw_payload,
    }


@router.post("/stores/{store_id}/taobao/test-pull")
async def test_store_taobao_pull(
    store_id: int = Path(..., ge=1),
    allow_real_request: bool = Query(False),
    payload: dict | None = Body(default=None),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """
    淘宝 test-pull。

    allow_real_request=False:
    - 只检查配置和授权，不发真实订单请求。

    allow_real_request=True:
    - 调用 taobao.trades.sold.get 拉一页摘要；
    - 逐单调用 taobao.trade.fullinfo.get 补详情；
    - 更新 connection 状态；
    - 不写 taobao_orders / taobao_order_items。
    """
    check_perm(db, current_user, ["config.store.read"])

    payload = payload or {}
    start_time = payload.get("start_time")
    end_time = payload.get("end_time")
    status = payload.get("status")
    page = int(payload.get("page") or 1)
    page_size = int(payload.get("page_size") or 50)

    try:
        app_config = await require_enabled_taobao_app_config(session)
        service = TaobaoPullService(
            session,
            config=build_taobao_top_config_from_model(app_config),
        )
        result = await service.check_pull_ready(
            store_id=store_id,
            allow_real_request=allow_real_request,
            start_time=start_time,
            end_time=end_time,
            page=page,
            page_size=page_size,
            status=status,
        )
    except (TaobaoPullServiceError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to run taobao test-pull: {exc}",
        ) from exc

    return {
        "ok": True,
        "data": {
            "store_id": result.store_id,
            "platform": result.platform,
            "executed_real_pull": result.executed_real_pull,
            "pull_ready": result.pull_ready,
            "status": result.status,
            "status_reason": result.status_reason,
            "orders_count": result.orders_count,
            "detailed_orders_count": result.detailed_orders_count,
            "page": result.page,
            "page_size": result.page_size,
            "has_more": result.has_more,
            "start_time": result.start_time,
            "end_time": result.end_time,
            "orders": [
                {
                    "tid": order.tid,
                    "status": order.status,
                    "type": order.type,
                    "created": order.created,
                    "pay_time": order.pay_time,
                    "modified": order.modified,
                    "receiver_name": order.receiver_name,
                    "receiver_mobile": order.receiver_mobile,
                    "receiver_address_summary": order.receiver_address_summary,
                    "payment": order.payment,
                    "total_fee": order.total_fee,
                    "items_count": order.items_count,
                    "detail_loaded": order.detail_loaded,
                    "detail": _detail_out(order),
                }
                for order in result.orders
            ],
        },
    }
