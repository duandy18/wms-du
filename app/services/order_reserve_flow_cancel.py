# app/services/order_reserve_flow_cancel.py
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter
from app.services.order_event_bus import OrderEventBus
from app.services.order_trace_helper import set_order_status_by_ref
from app.services.reservation_service import ReservationService
from app.services.soft_reserve_service import SoftReserveService

from app.services.order_reserve_flow_reserve import resolve_warehouse_for_order


async def cancel_flow(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
    lines: Sequence[Mapping[str, Any]],
    trace_id: Optional[str] = None,
) -> dict:
    platform_db = platform.upper()

    warehouse_id = await resolve_warehouse_for_order(
        session,
        platform=platform_db,
        shop_id=shop_id,
        ref=ref,
    )

    reservation_svc = ReservationService()
    soft_reserve_svc = SoftReserveService()

    existing = await reservation_svc.get_by_key(
        session,
        platform=platform_db,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        ref=ref,
    )

    if existing is None:
        status = "NOOP"
        reservation_id = None
    else:
        reservation_id, current_status = existing
        if current_status != "open":
            status = "NOOP"
        else:
            await soft_reserve_svc.release_reservation(
                session,
                reservation_id=reservation_id,
                reason="canceled",
                trace_id=trace_id,
            )
            status = "CANCELED"

    if status == "CANCELED":
        try:
            await set_order_status_by_ref(
                session,
                platform=platform_db,
                shop_id=shop_id,
                ref=ref,
                new_status="CANCELED",
            )
        except Exception:
            pass

    try:
        await OrderEventBus.order_canceled(
            session,
            ref=ref,
            platform=platform_db,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            status=status,
            trace_id=trace_id,
        )

        await AuditEventWriter.write(
            session,
            flow="OUTBOUND",
            event="RESERVE_CANCELED",
            ref=ref,
            trace_id=trace_id,
            meta={
                "platform": platform_db,
                "shop": shop_id,
                "warehouse_id": warehouse_id,
                "status": status,
            },
            auto_commit=False,
        )
    except Exception:
        pass

    return {
        "status": status,
        "ref": ref,
        "reservation_id": reservation_id,
    }
