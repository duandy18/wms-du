# app/api/routers/platform_orders_ingest_helpers.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.platform_order_resolve_service import norm_platform
from app.api.routers.platform_orders_ingest_schemas import PlatformOrderIngestIn


async def load_shop_id_by_store_id(session: AsyncSession, *, store_id: int, platform: str) -> str:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT shop_id, platform
                      FROM stores
                     WHERE id = :id
                     LIMIT 1
                    """
                ),
                {"id": int(store_id)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise LookupError("store not found")
    shop = row.get("shop_id")
    plat = (row.get("platform") or "").strip().upper()
    if not shop:
        raise LookupError("store shop_id empty")
    if plat and plat != norm_platform(platform):
        raise ValueError(f"platform mismatch: store.platform={plat} req.platform={norm_platform(platform)}")
    return str(shop)


def build_address(payload: PlatformOrderIngestIn) -> Optional[Dict[str, str]]:
    """
    address 结构直接喂给 OrderService.ingest(address=...)
    字段名对齐 order_address：receiver_name/receiver_phone/province/city/district/detail/zipcode

    最小策略：
    - 若完全没给任何地址字段 => None（保持兼容）
    - 若给了任意地址字段，但 province 为空 => 抛 ValueError（上层转 422）
    """
    raw = {
        "receiver_name": (payload.receiver_name or "").strip(),
        "receiver_phone": (payload.receiver_phone or "").strip(),
        "province": (payload.province or "").strip(),
        "city": (payload.city or "").strip(),
        "district": (payload.district or "").strip(),
        "detail": (payload.detail or "").strip(),
        "zipcode": (payload.zipcode or "").strip(),
    }

    has_any = any(v for v in raw.values())
    if not has_any:
        return None

    if not raw["province"]:
        raise ValueError("province 不能为空（履约路由至少需要省份）")

    return {k: v for k, v in raw.items() if v}


def build_items_payload(
    *,
    item_qty_map: Dict[int, int],
    items_brief: Dict[int, Dict[str, Any]],
    store_id: int,
    source: str,
) -> List[Dict[str, Any]]:
    """
    从 item_qty_map + items_brief 组装 OrderService.ingest 所需 items payload。
    """
    items_payload: List[Dict[str, Any]] = []
    for item_id in sorted(item_qty_map.keys()):
        need_qty = int(item_qty_map[item_id])
        brief = items_brief.get(item_id) or {}
        items_payload.append(
            {
                "item_id": int(item_id),
                "qty": need_qty,
                "sku_id": str(brief.get("sku") or ""),
                "title": str(brief.get("name") or ""),
                "extras": {"source": source, "store_id": int(store_id)},
            }
        )
    return items_payload


async def load_order_fulfillment_brief(
    session: AsyncSession, *, order_id: int
) -> Tuple[Optional[str], Optional[List[str]]]:
    """
    返回 (fulfillment_status, blocked_reasons)；无记录则返回 (None, None)。
    """
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT fulfillment_status, blocked_reasons
                      FROM order_fulfillment
                     WHERE order_id = :oid
                     LIMIT 1
                    """
                ),
                {"oid": int(order_id)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None, None

    fs = row.get("fulfillment_status")
    br = row.get("blocked_reasons")

    fulfillment_status = str(fs) if fs is not None else None

    blocked_reasons: Optional[List[str]] = None
    if isinstance(br, list):
        blocked_reasons = [str(x) for x in br]
    elif br is None:
        blocked_reasons = None
    else:
        # 极端情况下驱动可能返回字符串/其它形态；兜底成单元素字符串列表
        blocked_reasons = [str(br)]

    return fulfillment_status, blocked_reasons
