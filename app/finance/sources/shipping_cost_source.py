from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.services.common import to_decimal


class ShippingCostSource:
    """
    物流成本只读来源。

    边界：
    - 预估成本：shipping_records.cost_estimated
    - 账单成本：carrier_bill_items.total_amount / freight_amount / surcharge_amount
    - 对账差异：shipping_record_reconciliations.cost_diff / adjust_amount
    - 不读取采购
    - 不读取 OMS 销售收入
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
        by_carrier = await self._by_carrier(params)
        by_shop = await self._by_shop(params)
        return {
            "summary": summary,
            "daily": daily,
            "by_carrier": by_carrier,
            "by_shop": by_shop,
        }

    def _shipping_where(self, alias: str = "sr") -> str:
        return f"""
        DATE({alias}.created_at) BETWEEN :from_date AND :to_date
        AND (:platform = '' OR {alias}.platform = :platform)
        AND (:shop_id = '' OR {alias}.shop_id = :shop_id)
        AND NOT EXISTS (
          SELECT 1
            FROM platform_test_shops pts
           WHERE pts.code = 'DEFAULT'
             AND upper(pts.platform) = upper({alias}.platform)
             AND btrim(CAST(pts.shop_id AS text)) = btrim(CAST({alias}.shop_id AS text))
        )
        """

    async def _summary(self, params: dict[str, object]) -> dict[str, object]:
        sql = text(
            f"""
            WITH estimated AS (
              SELECT
                COUNT(*) AS shipment_count,
                COALESCE(SUM(COALESCE(sr.cost_estimated, 0)), 0) AS estimated_shipping_cost
                FROM shipping_records sr
               WHERE {self._shipping_where("sr")}
            ),
            billed AS (
              SELECT
                COALESCE(SUM(COALESCE(cbi.total_amount, COALESCE(cbi.freight_amount, 0) + COALESCE(cbi.surcharge_amount, 0))), 0) AS billed_shipping_cost
                FROM carrier_bill_items cbi
               WHERE DATE(COALESCE(cbi.business_time, cbi.created_at)) BETWEEN :from_date AND :to_date
            ),
            diff AS (
              SELECT
                COALESCE(SUM(COALESCE(r.cost_diff, 0)), 0) AS cost_diff,
                COALESCE(SUM(COALESCE(r.adjust_amount, 0)), 0) AS adjusted_cost
                FROM shipping_record_reconciliations r
                LEFT JOIN shipping_records sr ON sr.id = r.shipping_record_id
               WHERE DATE(r.created_at) BETWEEN :from_date AND :to_date
                 AND (
                   r.shipping_record_id IS NULL
                   OR ({self._shipping_where("sr")})
                 )
            )
            SELECT
              estimated.shipment_count,
              estimated.estimated_shipping_cost,
              billed.billed_shipping_cost,
              diff.cost_diff,
              diff.adjusted_cost
              FROM estimated, billed, diff
            """
        )
        row = (await self.session.execute(sql, params)).mappings().one()
        return {
            "shipment_count": int(row["shipment_count"] or 0),
            "estimated_shipping_cost": to_decimal(row["estimated_shipping_cost"]),
            "billed_shipping_cost": to_decimal(row["billed_shipping_cost"]),
            "cost_diff": to_decimal(row["cost_diff"]),
            "adjusted_cost": to_decimal(row["adjusted_cost"]),
        }

    async def _daily(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            WITH day_dim AS (
              SELECT generate_series(:from_date, :to_date, interval '1 day')::date AS day
            ),
            estimated AS (
              SELECT
                DATE(sr.created_at) AS day,
                COUNT(*) AS shipment_count,
                COALESCE(SUM(COALESCE(sr.cost_estimated, 0)), 0) AS estimated_shipping_cost
                FROM shipping_records sr
               WHERE {self._shipping_where("sr")}
               GROUP BY DATE(sr.created_at)
            ),
            billed AS (
              SELECT
                DATE(COALESCE(cbi.business_time, cbi.created_at)) AS day,
                COALESCE(SUM(COALESCE(cbi.total_amount, COALESCE(cbi.freight_amount, 0) + COALESCE(cbi.surcharge_amount, 0))), 0) AS billed_shipping_cost
                FROM carrier_bill_items cbi
               WHERE DATE(COALESCE(cbi.business_time, cbi.created_at)) BETWEEN :from_date AND :to_date
               GROUP BY DATE(COALESCE(cbi.business_time, cbi.created_at))
            ),
            diff AS (
              SELECT
                DATE(r.created_at) AS day,
                COALESCE(SUM(COALESCE(r.cost_diff, 0)), 0) AS cost_diff,
                COALESCE(SUM(COALESCE(r.adjust_amount, 0)), 0) AS adjusted_cost
                FROM shipping_record_reconciliations r
                LEFT JOIN shipping_records sr ON sr.id = r.shipping_record_id
               WHERE DATE(r.created_at) BETWEEN :from_date AND :to_date
                 AND (
                   r.shipping_record_id IS NULL
                   OR ({self._shipping_where("sr")})
                 )
               GROUP BY DATE(r.created_at)
            )
            SELECT
              d.day,
              COALESCE(e.shipment_count, 0) AS shipment_count,
              COALESCE(e.estimated_shipping_cost, 0) AS estimated_shipping_cost,
              COALESCE(b.billed_shipping_cost, 0) AS billed_shipping_cost,
              COALESCE(df.cost_diff, 0) AS cost_diff,
              COALESCE(df.adjusted_cost, 0) AS adjusted_cost
              FROM day_dim d
              LEFT JOIN estimated e ON e.day = d.day
              LEFT JOIN billed b ON b.day = d.day
              LEFT JOIN diff df ON df.day = d.day
             ORDER BY d.day ASC
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "day": row["day"],
                "shipment_count": int(row["shipment_count"] or 0),
                "estimated_shipping_cost": to_decimal(row["estimated_shipping_cost"]),
                "billed_shipping_cost": to_decimal(row["billed_shipping_cost"]),
                "cost_diff": to_decimal(row["cost_diff"]),
                "adjusted_cost": to_decimal(row["adjusted_cost"]),
            }
            for row in rows
        ]

    async def _by_carrier(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            WITH estimated AS (
              SELECT
                COALESCE(sr.carrier_code, '') AS carrier_code,
                COUNT(*) AS shipment_count,
                COALESCE(SUM(COALESCE(sr.cost_estimated, 0)), 0) AS estimated_shipping_cost
                FROM shipping_records sr
               WHERE {self._shipping_where("sr")}
               GROUP BY COALESCE(sr.carrier_code, '')
            ),
            billed AS (
              SELECT
                COALESCE(cbi.carrier_code, '') AS carrier_code,
                COALESCE(SUM(COALESCE(cbi.total_amount, COALESCE(cbi.freight_amount, 0) + COALESCE(cbi.surcharge_amount, 0))), 0) AS billed_shipping_cost
                FROM carrier_bill_items cbi
               WHERE DATE(COALESCE(cbi.business_time, cbi.created_at)) BETWEEN :from_date AND :to_date
               GROUP BY COALESCE(cbi.carrier_code, '')
            ),
            carrier_dim AS (
              SELECT carrier_code FROM estimated
              UNION
              SELECT carrier_code FROM billed
            )
            SELECT
              d.carrier_code,
              COALESCE(e.shipment_count, 0) AS shipment_count,
              COALESCE(e.estimated_shipping_cost, 0) AS estimated_shipping_cost,
              COALESCE(b.billed_shipping_cost, 0) AS billed_shipping_cost
              FROM carrier_dim d
              LEFT JOIN estimated e ON e.carrier_code = d.carrier_code
              LEFT JOIN billed b ON b.carrier_code = d.carrier_code
             WHERE d.carrier_code <> ''
             ORDER BY billed_shipping_cost DESC, estimated_shipping_cost DESC, d.carrier_code ASC
             LIMIT 100
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "carrier_code": str(row["carrier_code"]),
                "shipment_count": int(row["shipment_count"] or 0),
                "estimated_shipping_cost": to_decimal(row["estimated_shipping_cost"]),
                "billed_shipping_cost": to_decimal(row["billed_shipping_cost"]),
            }
            for row in rows
        ]

    async def _by_shop(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            WITH estimated AS (
              SELECT
                sr.platform,
                sr.shop_id,
                COUNT(*) AS shipment_count,
                COALESCE(SUM(COALESCE(sr.cost_estimated, 0)), 0) AS estimated_shipping_cost
                FROM shipping_records sr
               WHERE {self._shipping_where("sr")}
               GROUP BY sr.platform, sr.shop_id
            ),
            billed AS (
              SELECT
                sr.platform,
                sr.shop_id,
                COALESCE(SUM(COALESCE(cbi.total_amount, COALESCE(cbi.freight_amount, 0) + COALESCE(cbi.surcharge_amount, 0))), 0) AS billed_shipping_cost
                FROM shipping_record_reconciliations r
                JOIN shipping_records sr ON sr.id = r.shipping_record_id
                JOIN carrier_bill_items cbi ON cbi.id = r.carrier_bill_item_id
               WHERE DATE(r.created_at) BETWEEN :from_date AND :to_date
                 AND {self._shipping_where("sr")}
               GROUP BY sr.platform, sr.shop_id
            ),
            shop_dim AS (
              SELECT platform, shop_id FROM estimated
              UNION
              SELECT platform, shop_id FROM billed
            )
            SELECT
              d.platform,
              d.shop_id,
              COALESCE(e.shipment_count, 0) AS shipment_count,
              COALESCE(e.estimated_shipping_cost, 0) AS estimated_shipping_cost,
              COALESCE(b.billed_shipping_cost, 0) AS billed_shipping_cost
              FROM shop_dim d
              LEFT JOIN estimated e ON e.platform = d.platform AND e.shop_id = d.shop_id
              LEFT JOIN billed b ON b.platform = d.platform AND b.shop_id = d.shop_id
             ORDER BY estimated_shipping_cost DESC, billed_shipping_cost DESC, d.platform ASC, d.shop_id ASC
             LIMIT 100
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "platform": str(row["platform"]),
                "shop_id": str(row["shop_id"]),
                "shipment_count": int(row["shipment_count"] or 0),
                "estimated_shipping_cost": to_decimal(row["estimated_shipping_cost"]),
                "billed_shipping_cost": to_decimal(row["billed_shipping_cost"]),
            }
            for row in rows
        ]
