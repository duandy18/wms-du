# app/services/order_reserve_flow_reserve.py
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter
from app.services.order_event_bus import OrderEventBus
from app.services.order_trace_helper import set_order_status_by_ref
from app.services.order_utils import to_int_pos
from app.services.reservation_service import ReservationService
from app.services.soft_reserve_service import SoftReserveService
from app.services.stock_availability_service import StockAvailabilityService

from app.services.order_reserve_flow_types import extract_ext_order_no


async def resolve_warehouse_for_order(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
) -> int:
    plat = platform.upper()
    ext_order_no = extract_ext_order_no(plat, shop_id, ref)
    if not ext_order_no:
        raise ValueError(
            f"cannot resolve warehouse for order: invalid ref={ref!r}, "
            f"expected 'ORD:{plat}:{shop_id}:{{ext_order_no}}'"
        )

    row = await session.execute(
        text(
            """
            SELECT
              warehouse_id,
              fulfillment_status,
              blocked_detail,
              blocked_reasons
              FROM orders
             WHERE platform = :p
               AND shop_id  = :s
               AND ext_order_no = :o
             LIMIT 1
            """
        ),
        {"p": plat, "s": shop_id, "o": ext_order_no},
    )
    rec = row.first()
    if rec is None:
        raise ValueError(
            f"cannot resolve warehouse for order: order not found "
            f"platform={plat}, shop={shop_id}, ext_order_no={ext_order_no}"
        )

    warehouse_id = rec[0]
    fulfillment_status = rec[1]
    blocked_detail = rec[2]
    blocked_reasons = rec[3]

    if warehouse_id is None or int(warehouse_id) == 0:
        extra = []
        if fulfillment_status:
            extra.append(f"fulfillment_status={fulfillment_status}")
        if blocked_detail:
            extra.append(f"blocked_detail={blocked_detail}")
        if blocked_reasons:
            extra.append(f"blocked_reasons={blocked_reasons}")
        suffix = ("; " + ", ".join(extra)) if extra else ""
        raise ValueError(
            f"cannot resolve warehouse for order: "
            f"platform={plat}, shop={shop_id}, ext_order_no={ext_order_no}, "
            f"warehouse_id is NULL/0{suffix}"
        )

    return int(warehouse_id)


async def reserve_flow(
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

    target_qty: Dict[int, int] = {}
    for row in lines or ():
        item_id = row.get("item_id")
        qty = to_int_pos(row.get("qty"), default=0)
        if item_id is None or qty <= 0:
            continue
        item_id = int(item_id)
        target_qty[item_id] = target_qty.get(item_id, 0) + qty

    soft_reserve_svc = SoftReserveService()
    reservation_svc = ReservationService()

    existing = await reservation_svc.get_by_key(
        session,
        platform=platform_db,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        ref=ref,
    )

    existing_id: Optional[int] = None
    existing_status: Optional[str] = None
    old_qty: Dict[int, int] = {}

    if existing is not None:
        existing_id, existing_status = existing
        if existing_status != "open":
            raise ValueError(
                f"reservation {platform_db}:{shop_id}:{warehouse_id}:{ref} "
                f"already in status={existing_status}, cannot reserve again"
            )
        old_lines = await reservation_svc.get_lines(session, existing_id)
        for item_id, qty in old_lines:
            old_qty[int(item_id)] = int(qty)

    # ✅ anti-oversell：用事实层 raw available（允许负数）
    for item_id, new_qty in target_qty.items():
        prev_qty = old_qty.get(item_id, 0)
        incr = new_qty - prev_qty
        if incr <= 0:
            continue

        available_raw = await StockAvailabilityService.get_available_for_item(
            session,
            platform=platform_db,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            item_id=item_id,
        )

        if incr > int(available_raw):
            raise ValueError(
                f"insufficient available for item={item_id}: "
                f"need +{incr}, available={available_raw}, "
                f"platform={platform_db}, shop={shop_id}, wh={warehouse_id}"
            )

    if not target_qty:
        try:
            await AuditEventWriter.write(
                session,
                flow="OUTBOUND",
                event="RESERVE_NO_LINES",
                ref=ref,
                trace_id=trace_id,
                meta={
                    "platform": platform_db,
                    "shop": shop_id,
                    "warehouse_id": warehouse_id,
                },
                auto_commit=False,
            )
        except Exception:
            pass
        return {"status": "OK", "ref": ref, "lines": 0}

    expire_minutes = 30
    r = await soft_reserve_svc.persist(
        session,
        platform=platform_db,
        shop_id=shop_id,
        warehouse_id=warehouse_id,
        ref=ref,
        lines=[{"item_id": k, "qty": v} for k, v in target_qty.items()],
        expire_at=expire_minutes,
        trace_id=trace_id,
    )
    reservation_id = r.get("reservation_id")

    try:
        await set_order_status_by_ref(
            session,
            platform=platform_db,
            shop_id=shop_id,
            ref=ref,
            new_status="RESERVED",
        )
    except Exception:
        pass

    try:
        await OrderEventBus.order_reserved(
            session,
            ref=ref,
            platform=platform_db,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            lines=len(target_qty),
            trace_id=trace_id,
        )

        await AuditEventWriter.write(
            session,
            flow="OUTBOUND",
            event="RESERVE_APPLIED",
            ref=ref,
            trace_id=trace_id,
            meta={
                "platform": platform_db,
                "shop": shop_id,
                "warehouse_id": warehouse_id,
                "lines": len(target_qty),
            },
            auto_commit=False,
        )
    except Exception:
        pass

    return {
        "status": "OK",
        "ref": ref,
        "reservation_id": reservation_id,
        "lines": len(target_qty),
    }
