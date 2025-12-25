# app/api/routers/orders_fulfillment_v2_routes_3_ship.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.orders_fulfillment_v2_helpers import get_order_ref_and_trace_id
from app.api.routers.orders_fulfillment_v2_schemas import ShipRequest, ShipResponse
from app.services.order_event_bus import OrderEventBus
from app.services.ship_service import ShipService


def register(router: APIRouter) -> None:
    @router.post(
        "/{platform}/{shop_id}/{ext_order_no}/ship",
        response_model=ShipResponse,
    )
    async def order_ship(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        body: ShipRequest,
        session: AsyncSession = Depends(get_session),
    ):
        plat = platform.upper()

        order_ref, trace_id = await get_order_ref_and_trace_id(
            session=session,
            platform=plat,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )

        svc = ShipService(session=session)
        occurred_at = body.occurred_at or datetime.now(timezone.utc)

        lines_meta = [{"item_id": line.item_id, "qty": line.qty} for line in body.lines]
        meta: Dict[str, Any] = {
            "platform": plat,
            "shop_id": shop_id,
            "warehouse_id": int(body.warehouse_id),
            "occurred_at": occurred_at.isoformat(),
            "lines": lines_meta,
        }

        try:
            result = await svc.commit(
                ref=order_ref, platform=plat, shop_id=shop_id, trace_id=trace_id, meta=meta
            )

            try:
                await session.execute(
                    text(
                        """
                        UPDATE orders
                           SET status = :st,
                               updated_at = NOW()
                         WHERE platform = :p
                           AND shop_id  = :s
                           AND ext_order_no = :o
                        """
                    ),
                    {"st": "SHIPPED", "p": plat, "s": shop_id, "o": ext_order_no},
                )
            except Exception:
                pass

            try:
                await OrderEventBus.order_shipped(
                    session,
                    ref=order_ref,
                    platform=plat,
                    shop_id=shop_id,
                    warehouse_id=int(body.warehouse_id),
                    lines=lines_meta,
                    occurred_at=occurred_at,
                    trace_id=trace_id,
                )
            except Exception:
                pass

            await session.commit()
        except Exception:
            await session.rollback()
            raise

        return ShipResponse(
            status="OK" if result.get("ok") else "ERROR", ref=order_ref, event="SHIP_COMMIT"
        )
