# app/services/dev_orders_service_impl.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_ref_helper import make_order_ref


class DevOrdersService:
    """
    DevConsole 订单视图 / 事实视图 / 列表视图的服务层：

    - 不关心 Pydantic，只返回 Mapping / dict；
    - 路由层负责把结果包成响应模型。
    - ⚠️ Phase 5+：不再读取 orders.warehouse_id
      执行仓一律来自 order_fulfillment.actual_warehouse_id
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ----------------- 单订单头信息 ----------------- #

    async def get_order_head(
        self,
        platform: str,
        shop_id: str,
        ext_order_no: str,
    ) -> Optional[Mapping[str, Any]]:
        plat = platform.upper().strip()
        row = (
            (
                await self.session.execute(
                    text(
                        """
                        SELECT
                            o.id,
                            o.platform,
                            o.shop_id,
                            o.ext_order_no,
                            o.status,
                            o.trace_id,
                            o.created_at,
                            o.updated_at,
                            f.actual_warehouse_id  AS warehouse_id,
                            f.planned_warehouse_id AS service_warehouse_id,
                            f.fulfillment_status   AS fulfillment_status,
                            o.order_amount,
                            o.pay_amount
                          FROM orders o
                          LEFT JOIN order_fulfillment f
                            ON f.order_id = o.id
                         WHERE o.platform = :p
                           AND o.shop_id  = :s
                           AND o.ext_order_no = :o
                         LIMIT 1
                        """
                    ),
                    {"p": plat, "s": shop_id, "o": ext_order_no},
                )
            )
            .mappings()
            .first()
        )
        return row

    # ----------------- 单订单事实视图 ----------------- #

    async def get_order_facts(
        self,
        platform: str,
        shop_id: str,
        ext_order_no: str,
    ) -> Tuple[Mapping[str, Any], List[Dict[str, Any]]]:
        head = await self.get_order_head(platform, shop_id, ext_order_no)
        if head is None:
            raise ValueError(
                f"order not found: platform={platform.upper()}, "
                f"shop_id={shop_id}, ext_order_no={ext_order_no}"
            )

        order_id = int(head["id"])
        plat = str(head["platform"]).upper()
        s_id = str(head["shop_id"])
        ext_no = str(head["ext_order_no"])
        order_ref = make_order_ref(plat, s_id, ext_no)

        # 1) 订单行基础数据
        rows_items = (
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

        if not rows_items:
            return head, []

        ordered_map: Dict[int, Dict[str, Any]] = {}
        for r in rows_items:
            item_id = int(r["item_id"])
            ordered_map[item_id] = {
                "item_id": item_id,
                "sku_id": r.get("sku_id"),
                "title": r.get("title"),
                "qty_ordered": int(r.get("qty") or 0),
            }

        # 2) shipped（仅发货类 ledger）
        rows_shipped = (
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
                           AND (
                                 reason ILIKE 'SHIP%%'
                              OR reason = 'OUTBOUND_SHIP'
                           )
                         GROUP BY item_id
                        """
                    ),
                    {"ref": order_ref},
                )
            )
            .mappings()
            .all()
        )

        shipped_map: Dict[int, int] = {
            int(r["item_id"]): int(r.get("shipped_qty") or 0) for r in rows_shipped
        }

        # 3) returned（RMA 收货）
        rows_returned = (
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

        returned_map: Dict[int, int] = {
            int(r["item_id"]): int(r.get("returned_qty") or 0) for r in rows_returned
        }

        facts: List[Dict[str, Any]] = []
        for item_id, base in ordered_map.items():
            ordered_qty = base["qty_ordered"]
            shipped_qty = shipped_map.get(item_id, 0)
            returned_qty = returned_map.get(item_id, 0)
            remaining = max(min(ordered_qty, shipped_qty) - returned_qty, 0)

            facts.append(
                {
                    "item_id": item_id,
                    "sku_id": base["sku_id"],
                    "title": base["title"],
                    "qty_ordered": ordered_qty,
                    "qty_shipped": shipped_qty,
                    "qty_returned": returned_qty,
                    "qty_remaining_refundable": remaining,
                }
            )

        return head, facts

    # ----------------- 订单列表 / summary ----------------- #

    async def list_orders_summary(
        self,
        platform: Optional[str] = None,
        shop_id: Optional[str] = None,
        status: Optional[str] = None,
        time_from: Optional[datetime] = None,
        time_to: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Mapping[str, Any]]:
        clauses: List[str] = []
        params: Dict[str, Any] = {"limit": limit}

        if platform:
            clauses.append("o.platform = :p")
            params["p"] = platform.upper()
        if shop_id:
            clauses.append("o.shop_id = :s")
            params["s"] = shop_id
        if status:
            clauses.append("o.status = :st")
            params["st"] = status
        if time_from:
            clauses.append("o.created_at >= :from_ts")
            params["from_ts"] = time_from
        if time_to:
            clauses.append("o.created_at <= :to_ts")
            params["to_ts"] = time_to

        where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""

        rows = (
            (
                await self.session.execute(
                    text(
                        f"""
                        SELECT
                            o.id,
                            o.platform,
                            o.shop_id,
                            o.ext_order_no,
                            o.status,
                            o.created_at,
                            o.updated_at,
                            f.actual_warehouse_id  AS warehouse_id,
                            f.planned_warehouse_id AS service_warehouse_id,
                            f.fulfillment_status   AS fulfillment_status,
                            o.order_amount,
                            o.pay_amount
                          FROM orders o
                          LEFT JOIN order_fulfillment f
                            ON f.order_id = o.id
                          {where_sql}
                         ORDER BY o.created_at DESC, o.id DESC
                         LIMIT :limit
                        """
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )

        return rows
