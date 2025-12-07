# app/services/order_reserve_flow.py
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter
from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_event_bus import OrderEventBus
from app.services.order_trace_helper import set_order_status_by_ref
from app.services.order_utils import to_int_pos
from app.services.reservation_service import ReservationService
from app.services.soft_reserve_service import SoftReserveService


class OrderReserveFlow:
    """
    订单预占 / 取消流程中控：

    - reserve：构造/更新软预占 + anti-oversell + ORDER_RESERVED 事件 + status；
    - cancel：释放软预占 + ORDER_CANCELED 事件 + status。
    """

    @staticmethod
    async def _resolve_warehouse_for_order(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        ref: str,
    ) -> int:
        plat = platform.upper()
        ext_order_no = ref.split(":", 3)[-1] if ref.startswith(f"ORD:{plat}:{shop_id}:") else None
        if not ext_order_no:
            raise ValueError(
                f"cannot resolve warehouse for order: invalid ref={ref!r}, "
                f"expected 'ORD:{plat}:{shop_id}:{{ext_order_no}}'"
            )

        row = await session.execute(
            text(
                """
                SELECT warehouse_id
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
        if rec is None or not rec[0]:
            raise ValueError(
                f"cannot resolve warehouse for order: "
                f"platform={plat}, shop={shop_id}, ext_order_no={ext_order_no}, "
                f"warehouse_id is NULL/0"
            )
        return int(rec[0])

    @staticmethod
    async def reserve(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        ref: str,
        lines: Sequence[Mapping[str, Any]],
        trace_id: Optional[str] = None,
    ) -> dict:
        platform_db = platform.upper()

        warehouse_id = await OrderReserveFlow._resolve_warehouse_for_order(
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

        channel_svc = ChannelInventoryService()
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

        for item_id, new_qty in target_qty.items():
            prev_qty = old_qty.get(item_id, 0)
            incr = new_qty - prev_qty
            if incr <= 0:
                continue
            available_raw = await channel_svc.get_available_for_item(
                session=session,
                platform=platform_db,
                shop_id=shop_id,
                warehouse_id=warehouse_id,
                item_id=item_id,
            )
            if incr > available_raw:
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

        # status 更新
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

        # 事件
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

    @staticmethod
    async def cancel(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        ref: str,
        lines: Sequence[Mapping[str, Any]],
        trace_id: Optional[str] = None,
    ) -> dict:
        platform_db = platform.upper()

        warehouse_id = await OrderReserveFlow._resolve_warehouse_for_order(
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

        # status 更新
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

        # 事件
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
