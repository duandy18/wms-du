# app/services/order_reconcile_apply.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_reconcile_types import OrderReconcileResult


async def apply_counters(session: AsyncSession, result: OrderReconcileResult) -> None:
    """
    将 shipped/returned 回写到 order_items.shipped_qty/returned_qty；
    并基于对账结果推进 orders.status（终态口径）：

    - refundable_per_line = min(qty_ordered, qty_shipped)
    - total_refundable = sum(refundable_per_line)
    - total_returned = sum(qty_returned)

    状态推进（保守策略）：
    - total_returned == 0：不改 orders.status
    - 0 < total_returned < total_refundable：PARTIALLY_RETURNED
    - total_returned >= total_refundable 且 total_refundable > 0：RETURNED

    保护：
    - 不覆盖 CANCELED（避免取消单被回填逻辑误改）
    - 不提交事务，由调用方控制。
    """
    # 1) 回填 line counters
    for lf in result.lines:
        await session.execute(
            text(
                """
                UPDATE order_items
                   SET shipped_qty = :shipped,
                       returned_qty = :returned
                 WHERE order_id = :oid
                   AND item_id = :item_id
                """
            ),
            {
                "oid": result.order_id,
                "item_id": lf.item_id,
                "shipped": lf.qty_shipped,
                "returned": lf.qty_returned,
            },
        )

    # 2) 推进订单状态（基于汇总事实）
    total_refundable = 0
    total_returned = 0

    for lf in result.lines:
        refundable = min(int(lf.qty_ordered), int(lf.qty_shipped))
        total_refundable += refundable
        total_returned += int(lf.qty_returned)

    # 没有任何退货：不推进状态
    if total_returned <= 0:
        return

    # 有退货但没有可退基数（理论上不应发生）：不推进，避免乱改状态
    if total_refundable <= 0:
        return

    new_status = "PARTIALLY_RETURNED" if total_returned < total_refundable else "RETURNED"

    # 仅在非取消订单上推进状态（保守护栏）
    await session.execute(
        text(
            """
            UPDATE orders
               SET status = :st
             WHERE id = :oid
               AND COALESCE(status, '') <> 'CANCELED'
            """
        ),
        {"oid": result.order_id, "st": new_status},
    )
