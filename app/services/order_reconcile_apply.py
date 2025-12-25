# app/services/order_reconcile_apply.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_reconcile_types import OrderReconcileResult


async def apply_counters(session: AsyncSession, result: OrderReconcileResult) -> None:
    """
    将 shipped/returned 回写到 order_items.shipped_qty/returned_qty；
    不提交事务，由调用方控制。
    """
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
