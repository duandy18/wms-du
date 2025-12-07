# app/services/order_reconcile_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_ref_helper import make_order_ref


@dataclass
class OrderLineFact:
    item_id: int
    sku_id: str | None
    title: str | None
    qty_ordered: int
    qty_shipped: int
    qty_returned: int
    remaining_refundable: int


@dataclass
class OrderReconcileResult:
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    issues: List[str]
    lines: List[OrderLineFact]


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

    async def _load_order_head(
        self,
        order_id: int,
    ) -> Optional[dict]:
        row = (
            (
                await self.session.execute(
                    text(
                        """
                    SELECT
                        id,
                        platform,
                        shop_id,
                        ext_order_no
                      FROM orders
                     WHERE id = :oid
                     LIMIT 1
                    """
                    ),
                    {"oid": order_id},
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    async def _load_items(self, order_id: int) -> Dict[int, dict]:
        rows = (
            (
                await self.session.execute(
                    text(
                        """
                    SELECT
                        item_id,
                        sku_id,
                        title,
                        COALESCE(qty, 0) AS qty
                      FROM order_items
                     WHERE order_id = :oid
                    """
                    ),
                    {"oid": order_id},
                )
            )
            .mappings()
            .all()
        )
        result: Dict[int, dict] = {}
        for r in rows:
            item_id = int(r["item_id"])
            result[item_id] = {
                "sku_id": r.get("sku_id"),
                "title": r.get("title"),
                "qty_ordered": int(r.get("qty") or 0),
            }
        return result

    async def _load_shipped(
        self,
        platform: str,
        shop_id: str,
        ext_order_no: str,
    ) -> Dict[int, int]:
        # 统一用 OrderRefHelper 构造订单 ref
        order_ref = make_order_ref(platform, shop_id, ext_order_no)
        rows = (
            (
                await self.session.execute(
                    text(
                        """
                    SELECT
                        item_id,
                        SUM(
                            CASE WHEN delta < 0 THEN -delta ELSE 0 END
                        ) AS shipped_qty
                      FROM stock_ledger
                     WHERE ref = :ref
                     GROUP BY item_id
                    """
                    ),
                    {"ref": order_ref},
                )
            )
            .mappings()
            .all()
        )
        result: Dict[int, int] = {}
        for r in rows:
            result[int(r["item_id"])] = int(r.get("shipped_qty") or 0)
        return result

    async def _load_returned(self, order_id: int) -> Dict[int, int]:
        rows = (
            (
                await self.session.execute(
                    text(
                        """
                    SELECT
                        rtl.item_id,
                        SUM(COALESCE(rtl.committed_qty, 0)) AS returned_qty
                      FROM receive_task_lines AS rtl
                      JOIN receive_tasks AS rt
                        ON rt.id = rtl.task_id
                     WHERE rt.source_type = 'ORDER'
                       AND rt.source_id = :oid
                       AND rt.status = 'COMMITTED'
                     GROUP BY rtl.item_id
                    """
                    ),
                    {"oid": order_id},
                )
            )
            .mappings()
            .all()
        )
        result: Dict[int, int] = {}
        for r in rows:
            result[int(r["item_id"])] = int(r.get("returned_qty") or 0)
        return result

    async def reconcile_order(self, order_id: int) -> OrderReconcileResult:
        """
        对单个订单做事实对账：

        - 若订单不存在：抛 ValueError；
        - 结果中 issues 列出所有发现的问题（字符串描述）；
        - lines 包含每个 item 的事实信息（ordered/shipped/returned/remaining）。
        """
        head = await self._load_order_head(order_id)
        if head is None:
            raise ValueError(f"order not found: id={order_id}")

        platform = str(head["platform"]).upper()
        shop_id = str(head["shop_id"])
        ext_order_no = str(head["ext_order_no"])

        items_map = await self._load_items(order_id)
        shipped_map = await self._load_shipped(platform, shop_id, ext_order_no)
        returned_map = await self._load_returned(order_id)

        issues: List[str] = []
        lines: List[OrderLineFact] = []

        # 1) 针对订单行逐个对账
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

        # 2) ledger / RMA 中有 item，但 order_items 中没有的情况
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
        """
        从 ledger 和 RMA 事实中重算 shipped/returned，并写回 order_items：

        - 对当前订单的每个 item：
            UPDATE order_items
              SET shipped_qty = qty_shipped,
                  returned_qty = qty_returned
            WHERE order_id = :order_id AND item_id = :item_id
        - 不提交事务，由调用方控制。
        """
        result = await self.reconcile_order(order_id)

        for lf in result.lines:
            await self.session.execute(
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

    async def reconcile_orders_by_created_at(
        self,
        time_from: datetime,
        time_to: datetime,
        limit: int = 1000,
    ) -> List[OrderReconcileResult]:
        """
        按创建时间窗口批量对账一批订单：

        - 只根据 orders.created_at 过滤；
        - 返回每个订单的 OrderReconcileResult；
        - limit 用于限制本次最多处理多少条订单，防止一次扫太大。
        """
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT id
                      FROM orders
                     WHERE created_at >= :from_ts
                       AND created_at <= :to_ts
                     ORDER BY created_at, id
                     LIMIT :limit
                    """
                ),
                {
                    "from_ts": time_from,
                    "to_ts": time_to,
                    "limit": limit,
                },
            )
        ).fetchall()

        order_ids = [int(r[0]) for r in rows]
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
        """
        在指定时间窗口内，批量按订单 apply_counters：

        - 返回本次处理的订单数量；
        - 不提交事务，由调用方控制（适合在 CLI / dev API 中包一层事务）。
        """
        results = await self.reconcile_orders_by_created_at(
            time_from=time_from,
            time_to=time_to,
            limit=limit,
        )
        for res in results:
            await self.apply_counters(res.order_id)
        return len(results)
