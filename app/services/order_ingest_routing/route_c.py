# app/services/order_ingest_routing/route_c.py
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from .normalize import normalize_province_from_address
from .route_c_service_hit import resolve_service_hit
from .route_c_state import mark_fulfillment_blocked, mark_service_assigned


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
    ✅ Route C（收敛到“简单世界观”）

    只做“服务归属（service warehouse）”，不做库存判断、不做自动改派、不做候选扫描。

    写入目标（新主线）：
      - 命中 service warehouse → SERVICE_ASSIGNED：写 order_fulfillment.planned_warehouse_id
      - 命不中/省份缺失 → FULFILLMENT_BLOCKED：写 order_fulfillment.fulfillment_status + blocked detail

    兼容返回 payload：
      - service_warehouse_id 仍保留，用作 planned_warehouse_id 的兼容别名（便于旧调用方/调试工具读取）。
        但系统事实以 order_fulfillment 为准，orders 表不承载仓库归属。
    """
    if not items:
        return None

    plat_norm = (platform or "").upper().strip()

    prov = normalize_province_from_address(address)
    if not prov:
        return await mark_fulfillment_blocked(
            session,
            order_id=int(order_id),
            order_ref=order_ref,
            trace_id=trace_id,
            platform_norm=plat_norm,
            shop_id=shop_id,
            reasons_json='["PROVINCE_MISSING_OR_INVALID"]',
            detail="省份缺失：无法命中服务仓（必须显式提供 address.province）",
            province=None,
            city=None,
            service_warehouse_id=None,
            meta_extra={"reason": "PROVINCE_MISSING_OR_INVALID"},
            auto_commit=False,
        )

    hit = await resolve_service_hit(session, province=prov, address=address)
    swid = hit.service_warehouse_id

    if not swid:
        # mode=province：说明 warehouse_service_provinces 没配置该省
        # mode=city：说明 city-split 省，但 city 缺失/或 warehouse_service_cities 没配置该市
        reason = "NO_SERVICE_PROVINCE" if hit.mode == "province" else "NO_SERVICE_WAREHOUSE"
        detail = (
            f"无法命中服务仓：province={prov}"
            if hit.mode == "province"
            else f"无法命中服务仓：城市 {hit.city or '-'} 未配置服务仓"
        )
        return await mark_fulfillment_blocked(
            session,
            order_id=int(order_id),
            order_ref=order_ref,
            trace_id=trace_id,
            platform_norm=plat_norm,
            shop_id=shop_id,
            reasons_json=f'["{reason}"]',
            detail=detail,
            province=prov,
            city=hit.city,
            service_warehouse_id=None,
            meta_extra={"reason": reason, "mode": hit.mode, "city": hit.city},
            auto_commit=False,
        )

    return await mark_service_assigned(
        session,
        order_id=int(order_id),
        order_ref=order_ref,
        trace_id=trace_id,
        platform_norm=plat_norm,
        shop_id=shop_id,
        service_warehouse_id=int(swid),
        province=prov,
        city=hit.city,
        mode=hit.mode,
        auto_commit=False,
    )
