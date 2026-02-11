# app/api/routers/dev_fake_orders_replay.py
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import new_trace
from app.services.order_service import OrderService
from app.services.platform_order_resolve_service import (
    load_items_brief,
    norm_platform,
    resolve_platform_lines_to_items,
)

from app.api.routers.platform_orders_fact_repo import load_fact_lines_for_order, load_shop_id_by_store_id
from app.api.routers.platform_orders_shared import build_items_payload_from_item_qty_map


async def run_single_replay(
    session: AsyncSession,
    platform: str,
    store_id: int,
    ext_order_no: str,
) -> Dict[str, Any]:
    trace = new_trace("dev:/dev/fake-orders/replay")

    plat = norm_platform(platform)
    ext = str(ext_order_no or "").strip()

    shop_id = await load_shop_id_by_store_id(session, store_id=store_id)
    fact_lines = await load_fact_lines_for_order(
        session,
        platform=plat,
        store_id=store_id,
        ext_order_no=ext,
    )

    resolved_lines, unresolved, item_qty_map = await resolve_platform_lines_to_items(
        session,
        platform=plat,
        store_id=store_id,
        lines=fact_lines,
    )

    if not item_qty_map:
        return {
            "status": "UNRESOLVED",
            "resolved": [r.__dict__ for r in resolved_lines],
            "unresolved": unresolved,
        }

    item_ids = sorted(item_qty_map.keys())
    items_brief = await load_items_brief(session, item_ids=item_ids)

    items_payload = build_items_payload_from_item_qty_map(
        item_qty_map=item_qty_map,
        items_brief=items_brief,
        store_id=store_id,
        source="dev/fake-orders/replay",
    )

    r = await OrderService.ingest(
        session,
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext,
        occurred_at=None,
        buyer_name=None,
        buyer_phone=None,
        order_amount=0.0,
        pay_amount=0.0,
        items=items_payload,
        address=None,
        extras={"store_id": store_id, "source": "dev/fake-orders/replay"},
        trace_id=trace.trace_id,
    )

    await session.commit()

    return {
        "status": str(r.get("status") or "OK"),
        "resolved": [r.__dict__ for r in resolved_lines],
        "unresolved": unresolved,
    }
