from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.services.common import to_decimal


class OrderSalesSource:
    """
    订单销售只读来源。

    边界：
    - 只读 OMS 订单事实：orders / order_items
    - 不读取采购
    - 不读取发货辅助
    - 不计算利润
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def fetch(
        self,
        *,
        from_date: date,
        to_date: date,
        platform: str = "",
        shop_id: str = "",
    ) -> dict[str, Any]:
        params = {
            "from_date": from_date,
            "to_date": to_date,
            "platform": platform,
            "shop_id": shop_id,
        }

        summary = await self._summary(params)
        daily = await self._daily(params)
        by_shop = await self._by_shop(params)
        by_item = await self._by_item(params)
        top_orders = await self._top_orders(params)

        return {
            "summary": summary,
            "daily": daily,
            "by_shop": by_shop,
            "by_item": by_item,
            "top_orders": top_orders,
        }

    def _base_where(self) -> str:
        return """
        DATE(o.created_at) BETWEEN :from_date AND :to_date
        AND (:platform = '' OR o.platform = :platform)
        AND (:shop_id = '' OR o.shop_id = :shop_id)
        AND NOT EXISTS (
          SELECT 1
            FROM platform_test_shops pts
           WHERE pts.code = 'DEFAULT'
             AND upper(pts.platform) = upper(o.platform)
             AND btrim(CAST(pts.shop_id AS text)) = btrim(CAST(o.shop_id AS text))
        )
        """

    async def _summary(self, params: dict[str, object]) -> dict[str, object]:
        sql = text(
            f"""
            WITH order_values AS (
              SELECT COALESCE(o.pay_amount, o.order_amount, 0) AS order_value
                FROM orders o
               WHERE {self._base_where()}
            )
            SELECT
              COUNT(*) AS order_count,
              COALESCE(SUM(order_value), 0) AS revenue,
              CASE WHEN COUNT(*) > 0 THEN AVG(order_value) ELSE NULL END AS avg_order_value,
              percentile_disc(0.5) WITHIN GROUP (ORDER BY order_value) AS median_order_value
              FROM order_values
            """
        )
        row = (await self.session.execute(sql, params)).mappings().one()
        return {
            "order_count": int(row["order_count"] or 0),
            "revenue": to_decimal(row["revenue"]),
            "avg_order_value": to_decimal(row["avg_order_value"]).quantize(Decimal("0.01"))
            if row["avg_order_value"] is not None
            else None,
            "median_order_value": to_decimal(row["median_order_value"]).quantize(Decimal("0.01"))
            if row["median_order_value"] is not None
            else None,
        }

    async def _daily(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            WITH day_dim AS (
              SELECT generate_series(:from_date, :to_date, interval '1 day')::date AS day
            ),
            agg AS (
              SELECT
                DATE(o.created_at) AS day,
                COUNT(*) AS order_count,
                COALESCE(SUM(COALESCE(o.pay_amount, o.order_amount, 0)), 0) AS revenue
                FROM orders o
               WHERE {self._base_where()}
               GROUP BY DATE(o.created_at)
            )
            SELECT
              d.day,
              COALESCE(a.order_count, 0) AS order_count,
              COALESCE(a.revenue, 0) AS revenue
              FROM day_dim d
              LEFT JOIN agg a ON a.day = d.day
             ORDER BY d.day ASC
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "day": row["day"],
                "order_count": int(row["order_count"] or 0),
                "revenue": to_decimal(row["revenue"]),
            }
            for row in rows
        ]

    async def _by_shop(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            SELECT
              o.platform,
              o.shop_id,
              COUNT(*) AS order_count,
              COALESCE(SUM(COALESCE(o.pay_amount, o.order_amount, 0)), 0) AS revenue
              FROM orders o
             WHERE {self._base_where()}
             GROUP BY o.platform, o.shop_id
             ORDER BY revenue DESC, o.platform ASC, o.shop_id ASC
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "platform": str(row["platform"]),
                "shop_id": str(row["shop_id"]),
                "order_count": int(row["order_count"] or 0),
                "revenue": to_decimal(row["revenue"]),
            }
            for row in rows
        ]

    async def _by_item(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            SELECT
              oi.item_id,
              MAX(oi.sku_id) AS sku_id,
              MAX(oi.title) AS title,
              COALESCE(SUM(COALESCE(oi.qty, 0)), 0) AS qty_sold,
              COALESCE(SUM(COALESCE(oi.amount, COALESCE(oi.qty, 0) * COALESCE(oi.price, 0))), 0) AS revenue
              FROM orders o
              JOIN order_items oi ON oi.order_id = o.id
             WHERE {self._base_where()}
             GROUP BY oi.item_id
             HAVING COALESCE(SUM(COALESCE(oi.qty, 0)), 0) > 0
             ORDER BY revenue DESC, oi.item_id ASC
             LIMIT 100
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "item_id": int(row["item_id"]),
                "sku_id": row["sku_id"],
                "title": row["title"],
                "qty_sold": int(row["qty_sold"] or 0),
                "revenue": to_decimal(row["revenue"]),
            }
            for row in rows
        ]

    async def _top_orders(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            SELECT
              o.id AS order_id,
              o.platform,
              o.shop_id,
              o.ext_order_no,
              COALESCE(o.pay_amount, o.order_amount, 0) AS order_value,
              o.created_at
              FROM orders o
             WHERE {self._base_where()}
             ORDER BY order_value DESC, o.created_at DESC, o.id DESC
             LIMIT 50
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "order_id": int(row["order_id"]),
                "platform": str(row["platform"]),
                "shop_id": str(row["shop_id"]),
                "ext_order_no": str(row["ext_order_no"]),
                "order_value": to_decimal(row["order_value"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
