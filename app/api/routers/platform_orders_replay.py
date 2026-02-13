# app/api/routers/platform_orders_replay.py
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.problem import make_problem
from app.core.audit import new_trace
from app.services.platform_order_ingest_flow import PlatformOrderIngestFlow
from app.services.platform_order_resolve_service import norm_platform

from app.api.routers.platform_orders_address_fact_repo import (
    detect_unique_scope_for_ext,
    load_platform_order_address,
)
from app.api.routers.platform_orders_fact_repo import load_fact_lines_for_order, load_shop_id_by_store_id
from app.api.routers.platform_orders_replay_schemas import PlatformOrderReplayIn, PlatformOrderReplayOut

router = APIRouter(tags=["platform-orders"])


def _as_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _validate_address_has_province_or_code(address: Dict[str, Any]) -> bool:
    prov = _as_str(address.get("province"))
    prov_code = _as_str(address.get("province_code"))
    return bool(prov or prov_code)


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
    resolved_lines, unresolved, item_qty_map, items_payload = (
        await PlatformOrderIngestFlow.resolve_fact_lines_and_build_items_payload(
            session,
            platform=plat,
            store_id=store_id,
            lines=fact_lines,
            source="platform-orders/replay",
            extras={"store_id": store_id, "source": "platform-orders/replay"},
        )
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

    # ------------------------------------------------------------
    # ✅ Route B：订单级地址事实锚点（platform_order_addresses）
    # ------------------------------------------------------------
    # scope 必须显式给出，或可唯一推断（避免 PROD/DRILL 歧义）
    scope = _as_str(getattr(payload, "scope", None))
    if scope:
        scope = scope.upper()
    else:
        detected = await detect_unique_scope_for_ext(session, platform=plat, store_id=store_id, ext_order_no=ext)
        if detected is None:
            raise HTTPException(
                status_code=422,
                detail=make_problem(
                    status_code=422,
                    error_code="scope_missing",
                    message="scope 缺失且无法从地址事实表推断：请显式传入 scope（DRILL/PROD）",
                    context={"platform": plat, "store_id": store_id, "ext_order_no": ext, "trace_id": trace.trace_id},
                ),
            )
        if detected == "__AMBIGUOUS__":
            raise HTTPException(
                status_code=422,
                detail=make_problem(
                    status_code=422,
                    error_code="scope_ambiguous",
                    message="该 ext_order_no 在多个 scope 下均存在：replay 必须显式传入 scope（DRILL/PROD）",
                    context={"platform": plat, "store_id": store_id, "ext_order_no": ext, "trace_id": trace.trace_id},
                ),
            )
        scope = str(detected).upper()

    # address：默认从事实表回读；payload.address 允许显式覆盖
    address: Optional[Dict[str, Any]] = None

    if isinstance(getattr(payload, "address", None), dict):
        address = payload.address  # 显式覆盖（治理/调试用）

    if address is None:
        addr_row = await load_platform_order_address(session, scope=scope, platform=plat, store_id=store_id, ext_order_no=ext)
        if addr_row is not None:
            raw = addr_row.get("raw")
            if isinstance(raw, dict):
                address = raw

    if address is None or not isinstance(address, dict) or not _validate_address_has_province_or_code(address):
        # 不让 routing 背锅：缺地址事实直接在 replay 阶段拒绝
        raise HTTPException(
            status_code=422,
            detail=make_problem(
                status_code=422,
                error_code="address_missing",
                message="地址事实缺失或省份无效：replay 需要 province/province_code（优先从 platform_order_addresses 回读）",
                context={
                    "platform": plat,
                    "store_id": store_id,
                    "ext_order_no": ext,
                    "scope": scope,
                    "trace_id": trace.trace_id,
                },
            ),
        )

    out_dict = await PlatformOrderIngestFlow.run_tail_from_items_payload(
        session,
        platform=plat,
        shop_id=shop_id,
        store_id=store_id,
        ext_order_no=ext,
        occurred_at=None,
        buyer_name=None,
        buyer_phone=None,
        address=address,
        items_payload=items_payload,
        trace_id=trace.trace_id,
        source="platform-orders/replay",
        extras={"store_id": store_id, "source": "platform-orders/replay", "scope": scope},
        resolved=[r.__dict__ for r in resolved_lines],
        unresolved=unresolved,
        facts_written=0,
    )

    await session.commit()

    return PlatformOrderReplayOut(
        status=str(out_dict.get("status") or "OK"),
        id=out_dict.get("id"),
        ref=str(out_dict.get("ref") or f"ORD:{plat}:{shop_id}:{ext}"),
        platform=plat,
        store_id=store_id,
        ext_order_no=ext,
        facts_n=len(fact_lines),
        resolved=[r.__dict__ for r in resolved_lines],
        unresolved=unresolved,
        fulfillment_status=out_dict.get("fulfillment_status"),
        blocked_reasons=out_dict.get("blocked_reasons"),
    )
