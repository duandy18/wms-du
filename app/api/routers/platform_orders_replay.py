# app/api/routers/platform_orders_replay.py
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.problem import make_problem
from app.core.audit import new_trace
from app.services.order_service import OrderService
from app.services.platform_order_resolve_service import load_items_brief, norm_platform, resolve_platform_lines_to_items

from app.api.routers.platform_orders_fact_repo import load_fact_lines_for_order, load_shop_id_by_store_id
from app.api.routers.platform_orders_ingest_helpers import load_order_fulfillment_brief
from app.api.routers.platform_orders_replay_schemas import PlatformOrderReplayIn, PlatformOrderReplayOut
from app.api.routers.platform_orders_shared import build_items_payload_from_item_qty_map

router = APIRouter(tags=["platform-orders"])


@router.post(
    "/platform-orders/replay",
    response_model=PlatformOrderReplayOut,
    summary="平台订单事实重放解码：从 platform_order_lines 读取事实，复用 resolver + /orders ingest 主线幂等生成订单",
)
async def replay_platform_order(
    payload: PlatformOrderReplayIn = Body(...),
    session: AsyncSession = Depends(get_session),
):
    plat = norm_platform(payload.platform)
    store_id = int(payload.store_id)
    ext = str(payload.ext_order_no or "").strip()
    if not ext:
        raise HTTPException(
            status_code=422,
            detail=make_problem(
                status_code=422,
                error_code="request_validation_error",
                message="ext_order_no 不能为空",
                context={"platform": plat, "store_id": store_id},
            ),
        )

    trace = new_trace("http:/platform-orders/replay")

    try:
        shop_id = await load_shop_id_by_store_id(session, store_id=store_id)
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=make_problem(
                status_code=404,
                error_code="not_found",
                message="store_id 不存在",
                context={"platform": plat, "store_id": store_id, "ext_order_no": ext, "trace_id": trace.trace_id},
            ),
        )

    fact_lines = await load_fact_lines_for_order(session, platform=plat, store_id=store_id, ext_order_no=ext)

    if not fact_lines:
        return PlatformOrderReplayOut(
            status="NOT_FOUND",
            id=None,
            ref=f"ORD:{plat}:{shop_id}:{ext}",
            platform=plat,
            store_id=store_id,
            ext_order_no=ext,
            facts_n=0,
            resolved=[],
            unresolved=[{"reason": "FACTS_NOT_FOUND", "hint": "未找到该订单的事实行（platform/store_id/ext_order_no）"}],
            fulfillment_status=None,
            blocked_reasons=None,
        )

    # Phase N+2：不再补齐 filled_code；事实表中缺失将由 resolver 直接给出 MISSING_FILLED_CODE

    resolved_lines, unresolved, item_qty_map = await resolve_platform_lines_to_items(
        session,
        platform=plat,
        store_id=store_id,
        lines=fact_lines,
    )

    if not item_qty_map:
        return PlatformOrderReplayOut(
            status="UNRESOLVED",
            id=None,
            ref=f"ORD:{plat}:{shop_id}:{ext}",
            platform=plat,
            store_id=store_id,
            ext_order_no=ext,
            facts_n=len(fact_lines),
            resolved=[r.__dict__ for r in resolved_lines],
            unresolved=unresolved,
            fulfillment_status=None,
            blocked_reasons=None,
        )

    item_ids = sorted(item_qty_map.keys())
    items_brief = await load_items_brief(session, item_ids=item_ids)

    items_payload = build_items_payload_from_item_qty_map(
        item_qty_map=item_qty_map,
        items_brief=items_brief,
        store_id=store_id,
        source="platform-orders/replay",
    )

    r = await OrderService.ingest(
        session,
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext,
        occurred_at=None,
        buyer_name=None,
        buyer_phone=None,
        order_amount=0.0,
        pay_amount=0.0,
        items=items_payload,
        address=None,
        extras={"store_id": store_id, "source": "platform-orders/replay"},
        trace_id=trace.trace_id,
    )

    await session.commit()

    oid = int(r.get("id") or 0) if r.get("id") is not None else None
    ref = str(r.get("ref") or f"ORD:{plat}:{shop_id}:{ext}")

    fulfillment_status = None
    blocked_reasons = None
    if oid is not None:
        fulfillment_status, blocked_reasons = await load_order_fulfillment_brief(session, order_id=oid)

    return PlatformOrderReplayOut(
        status=str(r.get("status") or "OK"),
        id=oid,
        ref=ref,
        platform=plat,
        store_id=store_id,
        ext_order_no=ext,
        facts_n=len(fact_lines),
        resolved=[r.__dict__ for r in resolved_lines],
        unresolved=unresolved,
        fulfillment_status=fulfillment_status,
        blocked_reasons=blocked_reasons,
    )
