# app/services/order_ingest_routing/route_c_qty.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.warehouse_router import OrderContext, OrderLine, StockAvailabilityProvider, WarehouseRouter


def build_target_qty(items: Sequence[Mapping[str, Any]]) -> Dict[int, int]:
    """
    将订单 items 汇总成 {item_id: total_qty}。

    规则保持与原实现一致：
    - item_id 为空或 qty <= 0 的行忽略
    - qty 取 int(it.get("qty") or 0)
    """
    target_qty: Dict[int, int] = {}
    for it in items:
        item_id = it.get("item_id")
        qty = int(it.get("qty") or 0)
        if item_id is None or qty <= 0:
            continue
        iid = int(item_id)
        target_qty[iid] = target_qty.get(iid, 0) + qty
    return target_qty


@dataclass(frozen=True)
class InsufficientLine:
    item_id: int
    need: int
    available: int

    def to_dict(self) -> dict:
        return {"item_id": int(self.item_id), "need": int(self.need), "available": int(self.available)}


async def check_service_warehouse_sufficient(
    session: AsyncSession,
    *,
    platform_norm: str,
    shop_id: str,
    warehouse_id: int,
    target_qty: Mapping[int, int],
) -> List[dict]:
    """
    校验服务仓是否能整单履约。

    ✅ 统一口径：必须委托 WarehouseRouter.check_whole_order()（事实层裁决器）
    返回值保持与原实现一致：List[dict]，每个 dict 形如：
      {"item_id": ..., "need": ..., "available": ...}
    若全部满足则返回空数组。
    """
    lines = [
        OrderLine(item_id=int(item_id), qty=int(qty))
        for item_id, qty in (target_qty or {}).items()
        if int(item_id) > 0 and int(qty) > 0
    ]
    if not lines:
        return []

    ctx = OrderContext(platform=str(platform_norm), shop_id=str(shop_id), order_id="route_c")
    router = WarehouseRouter(availability_provider=StockAvailabilityProvider(session))
    r = await router.check_whole_order(ctx=ctx, warehouse_id=int(warehouse_id), lines=lines)

    if r.status == "OK":
        return []

    out: List[dict] = []
    for x in r.insufficient:
        out.append(InsufficientLine(item_id=int(x.item_id), need=int(x.need), available=int(x.available)).to_dict())
    return out
