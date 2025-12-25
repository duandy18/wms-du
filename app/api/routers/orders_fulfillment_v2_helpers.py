# app/api/routers/orders_fulfillment_v2_helpers.py
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService


async def get_order_ref_and_trace_id(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
) -> Tuple[str, Optional[str]]:
    plat = platform.upper()
    order_ref = f"ORD:{plat}:{shop_id}:{ext_order_no}"

    trace_id: Optional[str] = None

    try:
        trace_id = await OrderService.get_trace_id_for_order(
            session=session,
            platform=plat,
            shop_id=shop_id,
            ref=order_ref,
        )
    except Exception:
        trace_id = None

    if not trace_id:
        row = (
            (
                await session.execute(
                    text(
                        """
                    SELECT trace_id
                      FROM orders
                     WHERE platform = :p
                       AND shop_id  = :s
                       AND ext_order_no = :o
                     ORDER BY id DESC
                     LIMIT 1
                    """
                    ),
                    {"p": plat, "s": shop_id, "o": ext_order_no},
                )
            )
            .mappings()
            .first()
        )
        if row:
            trace_id = row.get("trace_id")

    return order_ref, trace_id


def extract_quote_snapshot(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not meta or not isinstance(meta, dict):
        return {}
    qs = meta.get("quote_snapshot")
    if isinstance(qs, dict):
        return qs
    return {}


def validate_quote_snapshot(qs: Dict[str, Any]) -> None:
    sq = qs.get("selected_quote")
    if not isinstance(sq, dict):
        raise HTTPException(
            status_code=422, detail="meta.quote_snapshot.selected_quote is required"
        )

    ta = sq.get("total_amount")
    if not isinstance(ta, (int, float)):
        raise HTTPException(
            status_code=422, detail="meta.quote_snapshot.selected_quote.total_amount must be number"
        )

    reasons = sq.get("reasons")
    if not isinstance(reasons, list) or len(reasons) == 0:
        raise HTTPException(
            status_code=422,
            detail="meta.quote_snapshot.selected_quote.reasons must be non-empty list",
        )


def extract_cost_estimated(qs: Dict[str, Any]) -> float:
    return float(qs["selected_quote"]["total_amount"])
