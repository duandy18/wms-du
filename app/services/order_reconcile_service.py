# app/services/order_reconcile_service.py
from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_reconcile_apply import apply_counters as _apply_counters
from app.services.order_reconcile_queries import (
    list_order_ids_by_created_at,
    load_items,
    load_order_head,
    load_returned,
    load_shipped,
)
from app.services.order_reconcile_types import OrderLineFact, OrderReconcileResult

__all__ = [
    "OrderLineFact",
    "OrderReconcileResult",
    "OrderReconcileService",
]


class OrderReconcileService:
    """
    针对单个订单的“事实层对账”服务：

    - 头信息来自 orders；
    - 行信息来自 order_items（qty）；
    - shipped 来自 stock_ledger(ref=ORD:PLAT:SHOP:ext_no, delta<0)；
    - returned 来自 receive_tasks(source_type='ORDER') + receive_task_lines.committed_qty；
    - remaining_refundable = max(min(ordered, shipped) - returned, 0)。

    提供能力：
      - reconcile_order(order_id)：只做检查与汇总；
      - apply_counters(order_id)：将 shipped/returned 回写到 order_items.shipped_qty/returned_qty；
      - reconcile_orders_by_created_at(time_from, time_to, limit)：批量对账；
      - apply_counters_for_range(time_from, time_to, limit)：批量回填 counters。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def reconcile_order(self, order_id: int) -> OrderReconcileResult:
        head = await load_order_head(self.session, order_id)
        if head is None:
            raise ValueError(f"order not found: id={order_id}")

        platform = str(head["platform"]).upper()
        shop_id = str(head["shop_id"])
        ext_order_no = str(head["ext_order_no"])

        items_map = await load_items(self.session, order_id)
        shipped_map = await load_shipped(
            self.session,
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )
        returned_map = await load_returned(self.session, order_id)

        issues: List[str] = []
        lines: List[OrderLineFact] = []

        for item_id, base in items_map.items():
            ordered = int(base["qty_ordered"])
            shipped = int(shipped_map.get(item_id, 0))
            returned = int(returned_map.get(item_id, 0))
            remaining = max(min(ordered, shipped) - returned, 0)

            if shipped > ordered:
                issues.append(f"item_id={item_id} shipped({shipped}) > ordered({ordered})")
            if returned > shipped:
                issues.append(f"item_id={item_id} returned({returned}) > shipped({shipped})")

            lines.append(
                OrderLineFact(
                    item_id=item_id,
                    sku_id=base["sku_id"],
                    title=base["title"],
                    qty_ordered=ordered,
                    qty_shipped=shipped,
                    qty_returned=returned,
                    remaining_refundable=remaining,
                )
            )

        for item_id in shipped_map.keys():
            if item_id not in items_map:
                issues.append(
                    f"ledger has shipped item_id={item_id}, but order_items has no row for it"
                )
        for item_id in returned_map.keys():
            if item_id not in items_map:
                issues.append(
                    f"RMA has returned item_id={item_id}, but order_items has no row for it"
                )

        return OrderReconcileResult(
            order_id=order_id,
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            issues=issues,
            lines=lines,
        )

    async def apply_counters(self, order_id: int) -> None:
        result = await self.reconcile_order(order_id)
        await _apply_counters(self.session, result)

    async def reconcile_orders_by_created_at(
        self,
        time_from: datetime,
        time_to: datetime,
        limit: int = 1000,
    ) -> List[OrderReconcileResult]:
        order_ids = await list_order_ids_by_created_at(
            self.session, time_from=time_from, time_to=time_to, limit=limit
        )
        results: List[OrderReconcileResult] = []
        for oid in order_ids:
            res = await self.reconcile_order(oid)
            results.append(res)
        return results

    async def apply_counters_for_range(
        self,
        time_from: datetime,
        time_to: datetime,
        limit: int = 1000,
    ) -> int:
        results = await self.reconcile_orders_by_created_at(
            time_from=time_from,
            time_to=time_to,
            limit=limit,
        )
        for res in results:
            await self.apply_counters(res.order_id)
        return len(results)
