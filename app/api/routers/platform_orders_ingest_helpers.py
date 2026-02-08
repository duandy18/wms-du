# app/api/routers/platform_orders_ingest_helpers.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.platform_order_resolve_service import norm_platform
from app.api.routers.platform_orders_ingest_schemas import PlatformOrderIngestIn
from app.services.order_ingest_routing.normalize import normalize_province_name


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

    Phase 2（省份 normalize）：
    - 允许常见非标准写法（如“河北”“ 河北 ”“内蒙”）规范化为标准省级行政区全称；
    - 无法识别则视为不合法（抛 ValueError），避免落脏数据污染履约路由。
    """
    prov_norm = normalize_province_name(payload.province)

    raw = {
        "receiver_name": (payload.receiver_name or "").strip(),
        "receiver_phone": (payload.receiver_phone or "").strip(),
        # ✅ province 以 normalize 后的标准全称写入（用于审计/解释/UI 展示 + 履约路由一致性）
        "province": (prov_norm or ""),
        "city": (payload.city or "").strip(),
        "district": (payload.district or "").strip(),
        "detail": (payload.detail or "").strip(),
        "zipcode": (payload.zipcode or "").strip(),
    }

    has_any = any(v for v in raw.values())
    if not has_any:
        return None

    if not raw["province"]:
        # 省份缺失或不合法（如“Hebei”等无法识别）
        raise ValueError("province 不能为空且必须是可识别的省级行政区（如：河北省）")

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
