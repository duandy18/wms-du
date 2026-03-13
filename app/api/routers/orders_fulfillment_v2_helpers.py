# app/api/routers/orders_fulfillment_v2_helpers.py
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService
from app.tms.quote_snapshot import (
    extract_cost_estimated as _extract_cost_estimated,
    extract_quote_snapshot as _extract_quote_snapshot,
    validate_quote_snapshot as _validate_quote_snapshot,
)
from app.tms.shipment import ShipmentApplicationError


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
    raw = _extract_quote_snapshot(dict(meta) if meta else None)
    return dict(raw)


def validate_quote_snapshot(qs: Dict[str, Any]) -> None:
    try:
        _validate_quote_snapshot(dict(qs))
    except ShipmentApplicationError as error:
        from fastapi import HTTPException

        raise HTTPException(status_code=error.status_code, detail=error.message) from error


def extract_cost_estimated(qs: Dict[str, Any]) -> float:
    return float(_extract_cost_estimated(dict(qs)))
