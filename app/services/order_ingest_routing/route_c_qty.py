# app/services/order_ingest_routing/route_c_qty.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.channel_inventory_service import ChannelInventoryService


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

    返回值保持与原实现一致：List[dict]，每个 dict 形如：
      {"item_id": ..., "need": ..., "available": ...}
    若全部满足则返回空数组。
    """
    channel_svc = ChannelInventoryService()
    insufficient: List[dict] = []
    for item_id, qty in target_qty.items():
        available_raw = await channel_svc.get_available_for_item(
            session=session,
            platform=platform_norm,
            shop_id=shop_id,
            warehouse_id=int(warehouse_id),
            item_id=int(item_id),
        )
        if int(qty) > int(available_raw):
            insufficient.append(
                InsufficientLine(item_id=int(item_id), need=int(qty), available=int(available_raw)).to_dict()
            )
    return insufficient
