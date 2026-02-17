# app/services/receive_task_commit_parts/order_return_side_effects.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_event_bus import OrderEventBus
from app.services.order_reconcile_service import OrderReconcileService


async def handle_order_return_side_effects(
    session: AsyncSession,
    *,
    order_id: int,
    warehouse_id: int,
    ref_fallback: str,
    returned_by_item: dict[int, int],
    trace_id: str | None,
) -> None:
    try:
        row = (
            await session.execute(
                text(
                    """
                    SELECT platform, shop_id, ext_order_no
                      FROM orders
                     WHERE id = :oid
                     LIMIT 1
                    """
                ),
                {"oid": order_id},
            )
        ).first()
        if row:
            plat, shop_id, ext_no = row
            order_ref = f"ORD:{str(plat).upper()}:{shop_id}:{ext_no}"
        else:
            order_ref = ref_fallback

        await OrderEventBus.order_returned(
            session,
            ref=order_ref,
            order_id=order_id,
            warehouse_id=warehouse_id,
            lines=[{"item_id": iid, "qty": qty} for iid, qty in returned_by_item.items()],
            trace_id=trace_id,
        )

        recon = OrderReconcileService(session)
        result = await recon.reconcile_order(order_id)
        await recon.apply_counters(order_id)

        full_returned = all(line_result.remaining_refundable == 0 for line_result in result.lines)
        new_status = "RETURNED" if full_returned else "PARTIALLY_RETURNED"

        await session.execute(
            text(
                """
                UPDATE orders
                   SET status = :st,
                       updated_at = NOW()
                 WHERE id = :oid
                """
            ),
            {"st": new_status, "oid": order_id},
        )

    except Exception:
        # ✅ 合同收敛阶段：不让副作用影响主线 commit（保持现状）
        pass
