# app/oms/orders/routers/orders_view_facts.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.oms.orders.repos.orders_view_facts_repo import (
    load_order_address,
    load_order_address_raw,
    load_order_facts_full,
    load_order_head_by_id,
    load_order_head_by_keys,
    load_order_head_raw_by_id,
    load_order_items_raw,
    load_platform_items,
)
from app.oms.orders.contracts.orders_view_facts import (
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
    return str(x)


async def _build_order_view_response(
    session: AsyncSession,
    *,
    order_id: int,
) -> OrderViewResponse:
    head = await load_order_head_by_id(session, order_id=order_id)
    oid = int(head["id"])

    items = await load_platform_items(session, order_id=oid)
    address = await load_order_address(session, order_id=oid)

    raw_head = await load_order_head_raw_by_id(session, order_id=oid)
    raw_items = await load_order_items_raw(session, order_id=oid)
    raw_address = await load_order_address_raw(session, order_id=oid)

    raw_bundle: Dict[str, Any] = {
        "orders": _json_friendly(raw_head) if raw_head is not None else None,
        "platform_order_lines": _json_friendly(items),
        "expanded_order_items": _json_friendly(raw_items),
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
        head = await load_order_head_by_keys(
            session, platform=platform, shop_id=shop_id, ext_order_no=ext_order_no
        )
        return await _build_order_view_response(session, order_id=int(head["id"]))

    @router.get(
        "/orders/{order_id}/view",
        response_model=OrderViewResponse,
    )
    async def order_view_by_id(
        order_id: int,
        session: AsyncSession = Depends(get_session),
    ) -> OrderViewResponse:
        return await _build_order_view_response(session, order_id=int(order_id))

    @router.get(
        "/orders/{platform}/{shop_id}/{ext_order_no}/facts",
        response_model=OrderFactsResponse,
    )
    async def order_facts(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        session: AsyncSession = Depends(get_session),
    ) -> OrderFactsResponse:
        head = await load_order_head_by_keys(
            session, platform=platform, shop_id=shop_id, ext_order_no=ext_order_no
        )
        facts = await load_order_facts_full(session, order_id=int(head["id"]))
        return OrderFactsResponse(
            ok=True,
            order_id=int(facts["order_id"]),
            platform=str(facts["platform"]),
            shop_id=str(facts["shop_id"]),
            ext_order_no=str(facts["ext_order_no"]),
            issues=list(facts["issues"]),
            items=[OrderFactItemOut(**x) for x in facts["items"]],
        )

    @router.get(
        "/orders/{order_id}/facts",
        response_model=OrderFactsResponse,
    )
    async def order_facts_by_id(
        order_id: int,
        session: AsyncSession = Depends(get_session),
    ) -> OrderFactsResponse:
        facts = await load_order_facts_full(session, order_id=int(order_id))
        return OrderFactsResponse(
            ok=True,
            order_id=int(facts["order_id"]),
            platform=str(facts["platform"]),
            shop_id=str(facts["shop_id"]),
            ext_order_no=str(facts["ext_order_no"]),
            issues=list(facts["issues"]),
            items=[OrderFactItemOut(**x) for x in facts["items"]],
        )
