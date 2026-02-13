# app/api/routers/dev_fake_orders_replay.py
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import new_trace
from app.services.platform_order_ingest_flow import PlatformOrderIngestFlow
from app.services.platform_order_resolve_service import norm_platform

from app.api.routers.platform_orders_address_fact_repo import (
    detect_unique_scope_for_ext,
    load_platform_order_address,
)
from app.api.routers.platform_orders_fact_repo import load_fact_lines_for_order, load_shop_id_by_store_id


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

    resolved_lines, unresolved, item_qty_map, items_payload = (
        await PlatformOrderIngestFlow.resolve_fact_lines_and_build_items_payload(
            session,
            platform=plat,
            store_id=store_id,
            lines=fact_lines,
            source="dev/fake-orders/replay",
            extras={"store_id": store_id, "source": "dev/fake-orders/replay"},
        )
    )

    if not item_qty_map:
        return {
            "status": "UNRESOLVED",
            "resolved": [r.__dict__ for r in resolved_lines],
            "unresolved": unresolved,
        }

    # ✅ 从订单级地址事实表回读
    scope = await detect_unique_scope_for_ext(session, platform=plat, store_id=store_id, ext_order_no=ext)
    if scope is None:
        return {
            "status": "UNRESOLVED",
            "resolved": [r.__dict__ for r in resolved_lines],
            "unresolved": unresolved,
            "error": "ADDRESS_FACT_MISSING: platform_order_addresses not found for this ext_order_no",
        }
    if scope == "__AMBIGUOUS__":
        return {
            "status": "UNRESOLVED",
            "resolved": [r.__dict__ for r in resolved_lines],
            "unresolved": unresolved,
            "error": "SCOPE_AMBIGUOUS: multiple scopes exist for this ext_order_no; replay requires explicit scope",
        }

    addr_row = await load_platform_order_address(session, scope=scope, platform=plat, store_id=store_id, ext_order_no=ext)
    if addr_row is None:
        return {
            "status": "UNRESOLVED",
            "resolved": [r.__dict__ for r in resolved_lines],
            "unresolved": unresolved,
            "error": "ADDRESS_FACT_MISSING: platform_order_addresses row missing (unexpected)",
        }

    # run_tail_from_items_payload 需要的是 address dict（我们用 raw 作为主承载）
    address = addr_row.get("raw") or {}
    if not isinstance(address, dict):
        address = {}

    out_dict = await PlatformOrderIngestFlow.run_tail_from_items_payload(
        session,
        platform=plat,
        shop_id=shop_id,
        store_id=store_id,
        ext_order_no=ext,
        occurred_at=None,
        buyer_name=None,
        buyer_phone=None,
        address=address,
        items_payload=items_payload,
        trace_id=trace.trace_id,
        source="dev/fake-orders/replay",
        extras={"store_id": store_id, "source": "dev/fake-orders/replay"},
        resolved=[r.__dict__ for r in resolved_lines],
        unresolved=unresolved,
        facts_written=0,
    )

    await session.commit()

    return {
        "status": str(out_dict.get("status") or "OK"),
        "resolved": [r.__dict__ for r in resolved_lines],
        "unresolved": unresolved,
    }
