# app/api/routers/orders_view_facts_routes.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Mapping

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.orders_view_facts_repo import (
    load_order_address,
    load_order_address_raw,
    load_order_facts,
    load_order_head_by_keys,
    load_order_head_raw_by_id,
    load_order_items_raw,
    load_platform_items,
)
from app.api.routers.orders_view_facts_schemas import (
    OrderFactItemOut,
    OrderFactsResponse,
    OrderViewResponse,
    PlatformOrderOut,
)


def _json_friendly(x: Any) -> Any:
    if x is None:
        return None
    if isinstance(x, (str, int, float, bool)):
        return x
    if isinstance(x, Decimal):
        try:
            return float(x)
        except Exception:
            return str(x)
    if isinstance(x, (datetime, date)):
        return x.isoformat()
    if isinstance(x, dict):
        return {str(k): _json_friendly(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json_friendly(v) for v in x]
    # 最后兜底：不让 JSON 序列化炸
    return str(x)


def _json_friendly_mapping(m: Mapping[str, Any]) -> Dict[str, Any]:
    return {str(k): _json_friendly(v) for k, v in m.items()}


def register(router) -> None:
    @router.get(
        "/orders/{platform}/{shop_id}/{ext_order_no}/view",
        response_model=OrderViewResponse,
    )
    async def order_view(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        session: AsyncSession = Depends(get_session),
    ) -> OrderViewResponse:
        head = await load_order_head_by_keys(session, platform=platform, shop_id=shop_id, ext_order_no=ext_order_no)
        oid = int(head["id"])

        items = await load_platform_items(session, order_id=oid)
        address = await load_order_address(session, order_id=oid)

        # raw：原始包（json-friendly），用于排障/对账/镜像“所见即所得”
        raw_head = await load_order_head_raw_by_id(session, order_id=oid)
        raw_items = await load_order_items_raw(session, order_id=oid)
        raw_address = await load_order_address_raw(session, order_id=oid)

        raw_bundle: Dict[str, Any] = {
            "orders": _json_friendly(raw_head) if raw_head is not None else None,
            "order_items": _json_friendly(raw_items),
            "order_address": _json_friendly(raw_address) if raw_address is not None else None,
        }

        order: Dict[str, Any] = {
            "id": oid,
            "platform": str(head["platform"]),
            "shop_id": str(head["shop_id"]),
            "ext_order_no": str(head["ext_order_no"]),
            "status": str(head["status"]) if head.get("status") is not None else None,
            "created_at": head["created_at"],
            "updated_at": head.get("updated_at"),
            "order_amount": float(head["order_amount"]) if head.get("order_amount") is not None else None,
            "pay_amount": float(head["pay_amount"]) if head.get("pay_amount") is not None else None,
            "buyer_name": str(head["buyer_name"]) if head.get("buyer_name") is not None else None,
            "buyer_phone": str(head["buyer_phone"]) if head.get("buyer_phone") is not None else None,
            "address": address,
            "items": items,
            "raw": raw_bundle,
        }
        return OrderViewResponse(ok=True, order=PlatformOrderOut(**order))

    @router.get(
        "/orders/{platform}/{shop_id}/{ext_order_no}/facts",
        response_model=OrderFactsResponse,
        deprecated=True,
    )
    async def order_facts(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        session: AsyncSession = Depends(get_session),
    ) -> OrderFactsResponse:
        """
        Deprecated：镜像详情页建议只用 /view（items 已包含 qty）。
        这里保留是为了兼容旧调用方（只输出 qty_ordered）。
        """
        head = await load_order_head_by_keys(session, platform=platform, shop_id=shop_id, ext_order_no=ext_order_no)
        oid = int(head["id"])

        items = await load_order_facts(session, order_id=oid)
        return OrderFactsResponse(ok=True, items=[OrderFactItemOut(**x) for x in items])
