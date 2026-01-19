# app/services/order_ingest_routing/route_c.py
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from .normalize import normalize_province_from_address
from .route_c_qty import build_target_qty, check_service_warehouse_sufficient
from .route_c_service_hit import resolve_service_hit
from .route_c_state import mark_fulfillment_blocked, mark_ready_to_fulfill


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
    路线 C（执行期约束满足式履约）：

    ✅ 默认：按省命中唯一服务仓（warehouse_service_provinces）
    ✅ 例外：若该省启用“按城市配置”（warehouse_service_city_split_provinces），则按市命中（warehouse_service_cities）

    - 系统不“选仓”，只做约束校验
    - 校验服务仓能否整单履约（数量不足则 BLOCKED）
    - 满足：标记 READY_TO_FULFILL，并写入 orders.warehouse_id / service_warehouse_id / fulfillment_warehouse_id
    - 不满足：标记 FULFILLMENT_BLOCKED + blocked_reasons/detail；不写 orders.warehouse_id（让下游 reserve 正确停下）
    """
    if not items:
        return None

    target_qty = build_target_qty(items)
    if not target_qty:
        return None

    plat_norm = platform.upper()

    province = normalize_province_from_address(address)
    if not province:
        return await mark_fulfillment_blocked(
            session,
            order_id=int(order_id),
            order_ref=order_ref,
            trace_id=trace_id,
            platform_norm=plat_norm,
            shop_id=shop_id,
            reasons_json='["NO_SERVICE_WAREHOUSE"]',
            detail="无法命中服务仓：订单收件省缺失",
            province=None,
            city=None,
            service_warehouse_id=None,
            meta_extra={"reason": "NO_SERVICE_WAREHOUSE", "considered": []},
            auto_commit=False,
        )

    # 只做命中，不写订单、不写审计
    hit = await resolve_service_hit(session, province=province, address=address)
    service_wid = hit.service_warehouse_id
    hit_mode = hit.mode  # "province" | "city"
    city = hit.city

    # split 省：要求 city；若缺失 city → BLOCKED
    if hit_mode == "city" and city is None:
        return await mark_fulfillment_blocked(
            session,
            order_id=int(order_id),
            order_ref=order_ref,
            trace_id=trace_id,
            platform_norm=plat_norm,
            shop_id=shop_id,
            reasons_json='["NO_SERVICE_WAREHOUSE"]',
            detail=f"无法命中服务仓：省份 {province} 已启用按城市配置，但订单收件市缺失",
            province=province,
            city=None,
            service_warehouse_id=None,
            meta_extra={"reason": "NO_SERVICE_WAREHOUSE", "mode": "city", "considered": []},
            auto_commit=False,
        )

    # province 未配置 / city 未配置 / 城市表不存在（视为未命中） → BLOCKED
    if service_wid is None:
        if hit_mode == "city":
            return await mark_fulfillment_blocked(
                session,
                order_id=int(order_id),
                order_ref=order_ref,
                trace_id=trace_id,
                platform_norm=plat_norm,
                shop_id=shop_id,
                reasons_json='["NO_SERVICE_WAREHOUSE"]',
                detail=f"无法命中服务仓：城市 {city} 未配置服务仓（省份 {province} 已启用按城市配置）",
                province=province,
                city=city,
                service_warehouse_id=None,
                meta_extra={"reason": "NO_SERVICE_WAREHOUSE", "mode": "city", "considered": []},
                auto_commit=False,
            )

        return await mark_fulfillment_blocked(
            session,
            order_id=int(order_id),
            order_ref=order_ref,
            trace_id=trace_id,
            platform_norm=plat_norm,
            shop_id=shop_id,
            reasons_json='["NO_SERVICE_WAREHOUSE"]',
            detail=f"无法命中服务仓：省份 {province} 未配置服务仓",
            province=province,
            city=None,
            service_warehouse_id=None,
            meta_extra={"reason": "NO_SERVICE_WAREHOUSE", "mode": "province", "considered": []},
            auto_commit=False,
        )

    # 数量校验：服务仓能否整单履约
    insufficient = await check_service_warehouse_sufficient(
        session,
        platform_norm=plat_norm,
        shop_id=shop_id,
        warehouse_id=int(service_wid),
        target_qty=target_qty,
    )
    if insufficient:
        return await mark_fulfillment_blocked(
            session,
            order_id=int(order_id),
            order_ref=order_ref,
            trace_id=trace_id,
            platform_norm=plat_norm,
            shop_id=shop_id,
            reasons_json='["INSUFFICIENT_QTY"]',
            detail=(
                f"服务仓库存不足：仓库 {service_wid} 无法整单履约（"
                f"{hit_mode}={province if hit_mode=='province' else city}"
                f")"
            ),
            province=province,
            city=city if hit_mode == "city" else None,
            service_warehouse_id=int(service_wid),
            meta_extra={
                "reason": "INSUFFICIENT_QTY",
                "insufficient": insufficient,
                "considered": [int(service_wid)],
                "mode": hit_mode,
            },
            auto_commit=False,
        )

    # READY：写入履约字段，并设置 orders.warehouse_id（让 reserve 主线继续）
    return await mark_ready_to_fulfill(
        session,
        order_id=int(order_id),
        order_ref=order_ref,
        trace_id=trace_id,
        platform_norm=plat_norm,
        shop_id=shop_id,
        warehouse_id=int(service_wid),
        province=province,
        city=city if hit_mode == "city" else None,
        mode=hit_mode,
        auto_commit=False,
    )
