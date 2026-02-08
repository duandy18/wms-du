# app/api/routers/platform_orders_ingest.py
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.problem import make_problem
from app.core.audit import new_trace
from app.services.order_service import OrderService
from app.services.platform_order_fact_service import upsert_platform_order_lines
from app.services.platform_order_resolve_service import (
    load_items_brief,
    norm_platform,
    norm_shop_id,
    resolve_platform_lines_to_items,
    resolve_store_id,
)

from app.api.routers.platform_orders_ingest_helpers import (
    build_address,
    build_items_payload,
    load_order_fulfillment_brief,
    load_shop_id_by_store_id,
)
from app.api.routers.platform_orders_ingest_schemas import (
    PlatformOrderIngestIn,
    PlatformOrderIngestOut,
)

# ✅ Phase 3.4 replay 拆分为独立模块
from app.api.routers.platform_orders_replay import router as replay_router

router = APIRouter(tags=["platform-orders"])


def _safe_preview(val: Any, max_len: int = 400) -> Optional[Any]:
    """
    仅用于错误 context 的轻量预览，避免把超大对象塞进响应/日志。
    """
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        s = str(val)
        return s if len(s) <= max_len else s[: max_len - 3] + "..."
    if isinstance(val, dict):
        out: Dict[str, Any] = {}
        for k, v in list(val.items())[:30]:
            out[str(k)] = _safe_preview(v, max_len=120)
        return out
    if isinstance(val, list):
        return [_safe_preview(v, max_len=120) for v in val[:20]]
    s = str(val)
    return s if len(s) <= max_len else s[: max_len - 3] + "..."


@router.post(
    "/platform-orders/ingest",
    response_model=PlatformOrderIngestOut,
    summary="平台订单接入（解码版）：先落事实，再解码（PSKU -> FSKU -> Items -> /orders 主线）",
)
async def ingest_platform_order(
    request: Request,
    payload: PlatformOrderIngestIn = Body(...),
    session: AsyncSession = Depends(get_session),
):
    trace = new_trace("http:/platform-orders/ingest")

    # -------------------------------------------------------------------------
    # Guard: 常见误用是把地址包成 address:{...}
    # 本接口地址字段为顶层字段（province/city/district/detail/zipcode/receiver_name/receiver_phone）
    # schema 配置 extra="ignore" 会静默丢弃未知字段；这里显式 422 提示，避免误判为路由/履约问题。
    # -------------------------------------------------------------------------
    try:
        raw = await request.json()
    except Exception:
        raw = None

    if isinstance(raw, dict) and "address" in raw:
        raise HTTPException(
            status_code=422,
            detail=make_problem(
                status_code=422,
                error_code="request_validation_error",
                message=(
                    "不支持 address:{...} 嵌套对象；请使用顶层字段 "
                    "province/city/district/detail/zipcode/receiver_name/receiver_phone。"
                ),
                context={
                    "trace_id": trace.trace_id,
                    "hint": "示例：{...,'province':'广东省',...}（不要写成 address:{'province':'广东省'}）",
                    "address_preview": _safe_preview(raw.get("address")),
                },
            ),
        )

    plat = norm_platform(payload.platform)

    # ✅ store_id 优先（内部治理）
    if payload.store_id is not None:
        store_id = int(payload.store_id)
        try:
            shop_id = norm_shop_id(await load_shop_id_by_store_id(session, store_id=store_id, platform=plat))
        except LookupError:
            raise HTTPException(
                status_code=404,
                detail=make_problem(
                    status_code=404,
                    error_code="not_found",
                    message="store_id 不存在",
                    context={
                        "platform": plat,
                        "store_id": store_id,
                        "ext_order_no": payload.ext_order_no,
                        "trace_id": trace.trace_id,
                    },
                ),
            )
        except ValueError as e:
            raise HTTPException(
                status_code=409,
                detail=make_problem(
                    status_code=409,
                    error_code="state_conflict",
                    message=str(e),
                    context={
                        "platform": plat,
                        "store_id": store_id,
                        "ext_order_no": payload.ext_order_no,
                        "trace_id": trace.trace_id,
                    },
                ),
            )
    else:
        # ⚠️ 兼容：外部输入 shop_id
        if payload.shop_id is None:
            raise HTTPException(
                status_code=422,
                detail=make_problem(
                    status_code=422,
                    error_code="request_validation_error",
                    message="store_id 或 shop_id 必须提供一个",
                    context={"platform": plat, "ext_order_no": payload.ext_order_no, "trace_id": trace.trace_id},
                ),
            )
        shop_id = norm_shop_id(payload.shop_id)
        store_id = await resolve_store_id(
            session,
            platform=plat,
            shop_id=shop_id,
            store_name=payload.store_name,
        )

    # ✅ 组装 address（最小闭环：至少省份）
    try:
        address = build_address(payload)
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=make_problem(
                status_code=422,
                error_code="request_validation_error",
                message=str(e),
                context={"platform": plat, "store_id": store_id, "ext_order_no": payload.ext_order_no},
            ),
        )

    raw_lines = [ln.model_dump() for ln in (payload.lines or [])]

    # ✅ Phase 3：先落事实（无论能否解码）
    facts_written = await upsert_platform_order_lines(
        session,
        platform=plat,
        shop_id=shop_id,
        store_id=store_id,
        ext_order_no=payload.ext_order_no,
        lines=raw_lines,
        raw_payload=payload.raw_payload,
    )

    resolved_lines, unresolved, item_qty_map = await resolve_platform_lines_to_items(
        session,
        platform=plat,
        store_id=store_id,
        lines=raw_lines,
    )

    if not item_qty_map:
        await session.commit()
        return PlatformOrderIngestOut(
            status="UNRESOLVED",
            id=None,
            ref=f"ORD:{plat}:{shop_id}:{payload.ext_order_no}",
            store_id=store_id,
            resolved=[r.__dict__ for r in resolved_lines],
            unresolved=unresolved,
            facts_written=facts_written,
            fulfillment_status=None,
            blocked_reasons=None,
        )

    item_ids = sorted(item_qty_map.keys())
    items_brief = await load_items_brief(session, item_ids=item_ids)

    items_payload = build_items_payload(
        item_qty_map=item_qty_map,
        items_brief=items_brief,
        store_id=store_id,
        source="platform-orders/ingest",
    )

    r = await OrderService.ingest(
        session,
        platform=plat,
        shop_id=shop_id,
        ext_order_no=payload.ext_order_no,
        occurred_at=payload.occurred_at,
        buyer_name=payload.buyer_name,
        buyer_phone=payload.buyer_phone,
        order_amount=0.0,
        pay_amount=0.0,
        items=items_payload,
        address=address,
        extras={"store_id": store_id, "source": "platform-orders/ingest"},
        trace_id=trace.trace_id,
    )

    await session.commit()

    oid = int(r.get("id") or 0) if r.get("id") is not None else None
    ref = str(r.get("ref") or f"ORD:{plat}:{shop_id}:{payload.ext_order_no}")
    status = str(r.get("status") or "OK")

    fulfillment_status = None
    blocked_reasons = None
    if oid is not None:
        fulfillment_status, blocked_reasons = await load_order_fulfillment_brief(session, order_id=oid)

    return PlatformOrderIngestOut(
        status=status,
        id=oid,
        ref=ref,
        store_id=store_id,
        resolved=[r.__dict__ for r in resolved_lines],
        unresolved=unresolved,
        facts_written=facts_written,
        fulfillment_status=fulfillment_status,
        blocked_reasons=blocked_reasons,
    )


# ✅ 把 replay 路由挂进来（不改 main 注册）
router.include_router(replay_router)
