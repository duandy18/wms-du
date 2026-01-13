# app/services/receive_task_commit_post_order.py
from __future__ import annotations

from typing import Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_event_bus import OrderEventBus
from app.services.order_reconcile_service import OrderReconcileService


async def post_commit_for_order_source(
    session: AsyncSession,
    *,
    task,
    ref: str,
    returned_by_item: Dict[int, int],
    trace_id: str | None,
) -> None:
    """
    ORDER 来源的 commit 后置处理（与原逻辑保持一致）：
    - 发 order_returned event
    - reconcile 并推进 orders.status
    """
    if task.source_type != "ORDER" or not task.source_id:
        return

    order_id = int(task.source_id)

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
            order_ref = ref

        await OrderEventBus.order_returned(
            session,
            ref=order_ref,
            order_id=order_id,
            warehouse_id=task.warehouse_id,
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
        # 与原逻辑保持一致：后置失败不阻断 commit
        return
