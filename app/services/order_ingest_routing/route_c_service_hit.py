# app/services/order_ingest_routing/route_c_service_hit.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .db_helpers import (
    is_city_split_province,
    resolve_service_warehouse_by_city,
    resolve_service_warehouse_by_province,
    table_exists,
)
from .normalize import normalize_city_from_address


@dataclass(frozen=True)
class ServiceHit:
    service_warehouse_id: Optional[int]
    mode: str  # "province" | "city"
    city: Optional[str]  # 仅 mode == "city" 有意义


async def resolve_service_hit(
    session: AsyncSession,
    *,
    province: str,
    address: Optional[Mapping[str, str]],
) -> ServiceHit:
    """
    Route C：只负责“服务仓命中”，不写订单，不写审计。
    语义保持：
    - 非 split 省：按 province 命中
    - split 省：要求 city；若城市表不存在视为未配置命中（返回 None）
    """
    city_split = await is_city_split_province(session, province=province)
    if not city_split:
        wid = await resolve_service_warehouse_by_province(session, province=province)
        return ServiceHit(service_warehouse_id=wid, mode="province", city=None)

    city = normalize_city_from_address(address)
    if not city:
        return ServiceHit(service_warehouse_id=None, mode="city", city=None)

    if not await table_exists(session, "warehouse_service_cities"):
        return ServiceHit(service_warehouse_id=None, mode="city", city=city)

    wid = await resolve_service_warehouse_by_city(session, city=city)
    return ServiceHit(service_warehouse_id=wid, mode="city", city=city)
