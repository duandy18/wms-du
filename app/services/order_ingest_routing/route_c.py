# app/services/order_ingest_routing/route_c.py
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.routing_candidates import resolve_candidate_warehouses_for_store
from app.services.warehouse_router import OrderContext, OrderLine, StockAvailabilityProvider, WarehouseRouter

from .route_c_qty import build_target_qty
from .route_c_state import mark_fulfillment_blocked, mark_ready_to_fulfill


def _province_from_address_soft(address: Optional[Mapping[str, str]]) -> Optional[str]:
    """
    Route C 使用“软省码”：
    - 测试与路由表里常用 P-XXX 这类省码
    - 不强制要求中文后缀（省/市/自治区）
    """
    if not address:
        return None
    p = str(address.get("province") or "").strip()
    return p or None


async def auto_route_warehouse_if_possible(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    order_id: int,
    order_ref: str,
    trace_id: Optional[str],
    items: Sequence[Mapping[str, Any]],
    address: Optional[Mapping[str, str]] = None,
) -> Optional[dict]:
    """
    ✅ Route C（统一选仓世界观版）

    契约（很硬）：
    - address.province 缺失/空 → 直接 FULFILLMENT_BLOCKED（不写 orders.warehouse_id）
    - 省份存在 → 候选集（store_province_routes / route_mode）→ WarehouseRouter 扫描 → READY/BLOCKED
    """
    if not items:
        return None

    target_qty = build_target_qty(items)
    if not target_qty:
        return None

    plat_norm = platform.upper()
    prov = _province_from_address_soft(address)

    # ✅ 关键护栏：省份缺失 → 不允许通过 FALLBACK“自动挑仓”
    if not prov:
        return await mark_fulfillment_blocked(
            session,
            order_id=int(order_id),
            order_ref=order_ref,
            trace_id=trace_id,
            platform_norm=plat_norm,
            shop_id=shop_id,
            reasons_json='["PROVINCE_MISSING_OR_INVALID"]',
            detail="省份缺失：Route C 不允许未定省份自动选仓（必须显式提供 address.province）",
            province=None,
            city=None,
            service_warehouse_id=None,
            meta_extra={
                "reason": "PROVINCE_MISSING_OR_INVALID",
                "considered": [],
            },
            auto_commit=False,
        )

    cand = await resolve_candidate_warehouses_for_store(
        session,
        platform=plat_norm,
        shop_id=shop_id,
        province=prov,
    )

    if not cand.candidate_warehouse_ids:
        reasons = (
            ["NO_PROVINCE_ROUTE_MATCH"]
            if cand.candidate_reason == "NO_PROVINCE_ROUTE_MATCH"
            else ["NO_WAREHOUSE_BOUND"]
        )
        return await mark_fulfillment_blocked(
            session,
            order_id=int(order_id),
            order_ref=order_ref,
            trace_id=trace_id,
            platform_norm=plat_norm,
            shop_id=shop_id,
            reasons_json=str(reasons).replace("'", '"'),
            detail=f"候选仓为空：{cand.candidate_reason}（route_mode={cand.route_mode}）",
            province=prov,
            city=None,
            service_warehouse_id=None,
            meta_extra={
                "reason": cand.candidate_reason,
                "route_mode": cand.route_mode,
                "fallback_used": cand.fallback_used,
                "considered": [],
            },
            auto_commit=False,
        )

    lines = [
        OrderLine(item_id=int(item_id), qty=int(qty))
        for item_id, qty in target_qty.items()
        if int(item_id) > 0 and int(qty) > 0
    ]
    if not lines:
        return None

    ctx = OrderContext(platform=plat_norm, shop_id=str(shop_id), order_id=int(order_id))
    router = WarehouseRouter(availability_provider=StockAvailabilityProvider(session))
    scan = await router.scan_warehouses(
        ctx=ctx,
        candidate_warehouse_ids=cand.candidate_warehouse_ids,
        lines=lines,
    )

    ok_ids = [int(r.warehouse_id) for r in scan if str(r.status) == "OK"]
    if not ok_ids:
        scan_dump = [r.to_dict() for r in scan]
        return await mark_fulfillment_blocked(
            session,
            order_id=int(order_id),
            order_ref=order_ref,
            trace_id=trace_id,
            platform_norm=plat_norm,
            shop_id=shop_id,
            reasons_json='["INSUFFICIENT_QTY"]',
            detail=f"候选仓全部不足：candidates={cand.candidate_warehouse_ids}",
            province=prov,
            city=None,
            service_warehouse_id=None,
            meta_extra={
                "reason": "INSUFFICIENT_QTY",
                "route_mode": cand.route_mode,
                "fallback_used": cand.fallback_used,
                "considered": cand.candidate_warehouse_ids,
                "scan": scan_dump,
            },
            auto_commit=False,
        )

    chosen = None
    ok_set = set(ok_ids)
    for wid in cand.candidate_warehouse_ids:
        if int(wid) in ok_set:
            chosen = int(wid)
            break
    if chosen is None:
        chosen = ok_ids[0]

    return await mark_ready_to_fulfill(
        session,
        order_id=int(order_id),
        order_ref=order_ref,
        trace_id=trace_id,
        platform_norm=plat_norm,
        shop_id=shop_id,
        warehouse_id=int(chosen),
        province=prov,
        city=None,
        mode="province_routes" if cand.candidate_reason == "PROVINCE_ROUTE_MATCH" else "fallback_bindings",
        auto_commit=False,
    )
