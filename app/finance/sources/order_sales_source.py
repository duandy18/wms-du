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
    - 只读财务侧订单销售事实表 finance_order_sales_lines；
    - 不让 finance read API 直接跨 OMS 表拼装页面数据；
    - 不读取采购；
    - 不读取发货辅助；
    - 不计算利润。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def fetch(
        self,
        *,
        from_date: date,
        to_date: date,
        platform: str = "",
        store_code: str = "",
        order_no: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        params = {
            "from_date": from_date,
            "to_date": to_date,
            "platform": platform,
            "store_code": store_code,
            "order_no": order_no,
            "limit": int(limit),
            "offset": int(offset),
        }

        summary = await self._summary(params)
        daily = await self._daily(params)
        by_store = await self._by_store(params)
        by_item = await self._by_item(params)
        items = await self._items(params)
        total = await self._total(params)

        return {
            "summary": summary,
            "daily": daily,
            "by_store": by_store,
            "by_item": by_item,
            "items": items,
            "total": total,
            "limit": int(limit),
            "offset": int(offset),
        }

    def _base_where(self, alias: str = "f") -> str:
        return f"""
        {alias}.order_date BETWEEN :from_date AND :to_date
        AND (:platform = '' OR {alias}.platform = :platform)
        AND (:store_code = '' OR {alias}.store_code = :store_code)
        AND (
          :order_no = ''
          OR {alias}.ext_order_no ILIKE ('%' || :order_no || '%')
          OR {alias}.order_ref ILIKE ('%' || :order_no || '%')
        )
        AND NOT EXISTS (
          SELECT 1
            FROM platform_test_stores pts
           WHERE pts.code = 'DEFAULT'
             AND (
               (pts.store_id IS NOT NULL AND pts.store_id = {alias}.store_id)
               OR (
                 upper(pts.platform) = upper({alias}.platform)
                 AND btrim(CAST(pts.store_code AS text)) = btrim(CAST({alias}.store_code AS text))
               )
             )
        )
        """

    async def _summary(self, params: dict[str, object]) -> dict[str, object]:
        sql = text(
            f"""
            WITH filtered AS (
              SELECT *
                FROM finance_order_sales_lines f
               WHERE {self._base_where("f")}
            ),
            order_values AS (
              SELECT
                order_id,
                MAX(COALESCE(pay_amount, order_amount, 0)) AS order_value
                FROM filtered
               GROUP BY order_id
            )
            SELECT
              (SELECT COUNT(*) FROM order_values) AS order_count,
              (SELECT COUNT(*) FROM filtered) AS line_count,
              (SELECT COALESCE(SUM(qty_sold), 0) FROM filtered) AS qty_sold,
              (SELECT COALESCE(SUM(order_value), 0) FROM order_values) AS revenue,
              (SELECT CASE WHEN COUNT(*) > 0 THEN AVG(order_value) ELSE NULL END FROM order_values) AS avg_order_value,
              (SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY order_value) FROM order_values) AS median_order_value
            """
        )
        row = (await self.session.execute(sql, params)).mappings().one()
        return {
            "order_count": int(row["order_count"] or 0),
            "line_count": int(row["line_count"] or 0),
            "qty_sold": int(row["qty_sold"] or 0),
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
            filtered AS (
              SELECT *
                FROM finance_order_sales_lines f
               WHERE {self._base_where("f")}
            ),
            order_values AS (
              SELECT
                order_date AS day,
                order_id,
                MAX(COALESCE(pay_amount, order_amount, 0)) AS order_value
                FROM filtered
               GROUP BY order_date, order_id
            ),
            order_agg AS (
              SELECT
                day,
                COUNT(*) AS order_count,
                COALESCE(SUM(order_value), 0) AS revenue
                FROM order_values
               GROUP BY day
            ),
            line_agg AS (
              SELECT
                order_date AS day,
                COUNT(*) AS line_count,
                COALESCE(SUM(qty_sold), 0) AS qty_sold
                FROM filtered
               GROUP BY order_date
            )
            SELECT
              d.day,
              COALESCE(oa.order_count, 0) AS order_count,
              COALESCE(la.line_count, 0) AS line_count,
              COALESCE(la.qty_sold, 0) AS qty_sold,
              COALESCE(oa.revenue, 0) AS revenue
              FROM day_dim d
              LEFT JOIN order_agg oa ON oa.day = d.day
              LEFT JOIN line_agg la ON la.day = d.day
             ORDER BY d.day ASC
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "day": row["day"],
                "order_count": int(row["order_count"] or 0),
                "line_count": int(row["line_count"] or 0),
                "qty_sold": int(row["qty_sold"] or 0),
                "revenue": to_decimal(row["revenue"]),
            }
            for row in rows
        ]

    async def _by_store(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            WITH filtered AS (
              SELECT *
                FROM finance_order_sales_lines f
               WHERE {self._base_where("f")}
            ),
            order_values AS (
              SELECT
                platform,
                store_code,
                store_name,
                order_id,
                MAX(COALESCE(pay_amount, order_amount, 0)) AS order_value
                FROM filtered
               GROUP BY platform, store_code, store_name, order_id
            ),
            order_agg AS (
              SELECT
                platform,
                store_code,
                store_name,
                COUNT(*) AS order_count,
                COALESCE(SUM(order_value), 0) AS revenue
                FROM order_values
               GROUP BY platform, store_code, store_name
            ),
            line_agg AS (
              SELECT
                platform,
                store_code,
                store_name,
                COUNT(*) AS line_count,
                COALESCE(SUM(qty_sold), 0) AS qty_sold
                FROM filtered
               GROUP BY platform, store_code, store_name
            )
            SELECT
              oa.platform,
              oa.store_code,
              oa.store_name,
              oa.order_count,
              COALESCE(la.line_count, 0) AS line_count,
              COALESCE(la.qty_sold, 0) AS qty_sold,
              oa.revenue
              FROM order_agg oa
              LEFT JOIN line_agg la
                ON la.platform = oa.platform
               AND la.store_code = oa.store_code
               AND COALESCE(la.store_name, '') = COALESCE(oa.store_name, '')
             ORDER BY oa.revenue DESC, oa.platform ASC, oa.store_code ASC
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "platform": str(row["platform"]),
                "store_code": str(row["store_code"]),
                "store_name": row["store_name"],
                "order_count": int(row["order_count"] or 0),
                "line_count": int(row["line_count"] or 0),
                "qty_sold": int(row["qty_sold"] or 0),
                "revenue": to_decimal(row["revenue"]),
            }
            for row in rows
        ]

    async def _by_item(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            SELECT
              f.item_id,
              MAX(i.sku) AS item_sku,
              MAX(i.name) AS item_name,
              MAX(f.sku_id) AS sku_id,
              MAX(f.title) AS title,
              COALESCE(SUM(f.qty_sold), 0) AS qty_sold,
              COALESCE(SUM(f.line_amount), 0) AS revenue
              FROM finance_order_sales_lines f
              LEFT JOIN items i
                ON i.id = f.item_id
             WHERE {self._base_where("f")}
             GROUP BY f.item_id
             HAVING COALESCE(SUM(f.qty_sold), 0) > 0
             ORDER BY revenue DESC, f.item_id ASC
             LIMIT 100
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "item_id": int(row["item_id"]),
                "item_sku": row["item_sku"],
                "item_name": row["item_name"],
                "sku_id": row["sku_id"],
                "title": row["title"],
                "qty_sold": int(row["qty_sold"] or 0),
                "revenue": to_decimal(row["revenue"]),
            }
            for row in rows
        ]

    async def _total(self, params: dict[str, object]) -> int:
        sql = text(
            f"""
            SELECT COUNT(*) AS total
              FROM finance_order_sales_lines f
             WHERE {self._base_where("f")}
            """
        )
        return int((await self.session.execute(sql, params)).scalar_one() or 0)

    async def _items(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            SELECT
              f.id,
              f.order_id,
              f.order_item_id,
              f.platform,
              f.store_id,
              f.store_code,
              f.store_name,
              f.ext_order_no,
              f.order_ref,
              f.order_status,
              f.order_created_at,
              f.order_date,
              f.receiver_province,
              f.receiver_city,
              f.receiver_district,
              CASE
                WHEN ofl.actual_warehouse_id IS NOT NULL THEN ofl.actual_warehouse_id
                WHEN ofl.planned_warehouse_id IS NOT NULL THEN ofl.planned_warehouse_id
                ELSE NULL
              END AS warehouse_id,
              COALESCE(wha.name, whp.name) AS warehouse_name,
              CASE
                WHEN ofl.actual_warehouse_id IS NOT NULL THEN 'actual'
                WHEN ofl.planned_warehouse_id IS NOT NULL THEN 'planned'
                ELSE 'none'
              END AS warehouse_source,
              f.item_id,
              i.sku AS item_sku,
              i.name AS item_name,
              f.sku_id,
              f.title,
              f.qty_sold,
              f.unit_price,
              f.discount_amount,
              f.line_amount,
              f.order_amount,
              f.pay_amount
              FROM finance_order_sales_lines f
              LEFT JOIN order_fulfillment ofl
                ON ofl.order_id = f.order_id
              LEFT JOIN warehouses whp
                ON whp.id = ofl.planned_warehouse_id
              LEFT JOIN warehouses wha
                ON wha.id = ofl.actual_warehouse_id
              LEFT JOIN items i
                ON i.id = f.item_id
             WHERE {self._base_where("f")}
             ORDER BY f.order_created_at DESC, f.id DESC
             LIMIT :limit OFFSET :offset
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "id": int(row["id"]),
                "order_id": int(row["order_id"]),
                "order_item_id": int(row["order_item_id"]),
                "platform": str(row["platform"]),
                "store_id": int(row["store_id"]),
                "store_code": str(row["store_code"]),
                "store_name": row["store_name"],
                "ext_order_no": str(row["ext_order_no"]),
                "order_ref": str(row["order_ref"]),
                "order_status": row["order_status"],
                "order_created_at": row["order_created_at"],
                "order_date": row["order_date"],
                "receiver_province": row["receiver_province"],
                "receiver_city": row["receiver_city"],
                "receiver_district": row["receiver_district"],
                "warehouse_id": int(row["warehouse_id"]) if row["warehouse_id"] is not None else None,
                "warehouse_name": row["warehouse_name"],
                "warehouse_source": str(row["warehouse_source"]),
                "item_id": int(row["item_id"]),
                "item_sku": row["item_sku"],
                "item_name": row["item_name"],
                "sku_id": row["sku_id"],
                "title": row["title"],
                "qty_sold": int(row["qty_sold"] or 0),
                "unit_price": to_decimal(row["unit_price"]) if row["unit_price"] is not None else None,
                "discount_amount": to_decimal(row["discount_amount"])
                if row["discount_amount"] is not None
                else None,
                "line_amount": to_decimal(row["line_amount"]),
                "order_amount": to_decimal(row["order_amount"]) if row["order_amount"] is not None else None,
                "pay_amount": to_decimal(row["pay_amount"]) if row["pay_amount"] is not None else None,
            }
            for row in rows
        ]
