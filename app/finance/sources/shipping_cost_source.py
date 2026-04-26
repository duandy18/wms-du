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
    - 财务物流成本第一阶段以 finance_shipping_cost_lines 为唯一 read source；
    - 一行 = 一条 shipping_records 包裹级发货事实；
    - 当前只承载预计物流成本；
    - 实际账单 / 对账差异 / 利润分析后置，不混入第一版物流成本明细口径。
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
        by_provider = await self._by_provider(params)
        by_shop = await self._by_shop(params)
        return {
            "summary": summary,
            "daily": daily,
            "by_carrier": by_provider,
            "by_shop": by_shop,
        }

    async def fetch_shipping_ledger(
        self,
        *,
        from_date: date | None,
        to_date: date | None,
        platform: str = "",
        shop_id: str = "",
        warehouse_id: int | None = None,
        shipping_provider_id: int | None = None,
        order_keyword: str = "",
        tracking_no: str = "",
    ) -> dict[str, Any]:
        where_sql, params = self._build_ledger_filters(
            from_date=from_date,
            to_date=to_date,
            platform=platform,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            shipping_provider_id=shipping_provider_id,
            order_keyword=order_keyword,
            tracking_no=tracking_no,
        )

        sql = text(
            f"""
            SELECT
              shipping_record_id,
              platform,
              shop_id,
              shop_name,
              order_ref,
              package_no,
              tracking_no,
              warehouse_id,
              warehouse_name,
              shipping_provider_id,
              shipping_provider_code,
              shipping_provider_name,
              shipped_time,
              shipped_date,
              dest_province,
              dest_city,
              gross_weight_kg,
              cost_estimated
            FROM finance_shipping_cost_lines f
            WHERE {where_sql}
            ORDER BY shipped_time DESC, shipping_record_id DESC
            LIMIT 500
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return {"rows": [dict(row) for row in rows]}

    async def fetch_shipping_ledger_options(
        self,
        *,
        from_date: date | None,
        to_date: date | None,
        platform: str = "",
        shop_id: str = "",
        warehouse_id: int | None = None,
        shipping_provider_id: int | None = None,
    ) -> dict[str, Any]:
        where_sql, params = self._build_ledger_filters(
            from_date=from_date,
            to_date=to_date,
            platform=platform,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            shipping_provider_id=shipping_provider_id,
            order_keyword="",
            tracking_no="",
        )

        shops = (
            await self.session.execute(
                text(
                    f"""
                    SELECT
                      platform,
                      shop_id,
                      MAX(shop_name) AS shop_name
                    FROM finance_shipping_cost_lines f
                    WHERE {where_sql}
                    GROUP BY platform, shop_id
                    ORDER BY platform ASC, shop_id ASC
                    LIMIT 500
                    """
                ),
                params,
            )
        ).mappings().all()

        warehouses = (
            await self.session.execute(
                text(
                    f"""
                    SELECT
                      warehouse_id,
                      MAX(warehouse_name) AS warehouse_name
                    FROM finance_shipping_cost_lines f
                    WHERE {where_sql}
                    GROUP BY warehouse_id
                    ORDER BY MAX(warehouse_name) ASC, warehouse_id ASC
                    LIMIT 500
                    """
                ),
                params,
            )
        ).mappings().all()

        providers = (
            await self.session.execute(
                text(
                    f"""
                    SELECT
                      shipping_provider_id,
                      MAX(shipping_provider_code) AS shipping_provider_code,
                      MAX(shipping_provider_name) AS shipping_provider_name
                    FROM finance_shipping_cost_lines f
                    WHERE {where_sql}
                    GROUP BY shipping_provider_id
                    ORDER BY MAX(shipping_provider_name) ASC NULLS LAST, shipping_provider_id ASC
                    LIMIT 500
                    """
                ),
                params,
            )
        ).mappings().all()

        return {
            "shops": [dict(row) for row in shops],
            "warehouses": [dict(row) for row in warehouses],
            "providers": [dict(row) for row in providers],
        }

    def _base_where(self, alias: str = "f") -> str:
        return f"""
        {alias}.shipped_date BETWEEN :from_date AND :to_date
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

    def _finance_test_shop_exclusion(self, alias: str = "f") -> str:
        return f"""
        NOT EXISTS (
          SELECT 1
            FROM platform_test_shops pts
           WHERE pts.code = 'DEFAULT'
             AND upper(pts.platform) = upper({alias}.platform)
             AND btrim(CAST(pts.shop_id AS text)) = btrim(CAST({alias}.shop_id AS text))
        )
        """

    def _build_ledger_filters(
        self,
        *,
        from_date: date | None,
        to_date: date | None,
        platform: str,
        shop_id: str,
        warehouse_id: int | None,
        shipping_provider_id: int | None,
        order_keyword: str,
        tracking_no: str,
    ) -> tuple[str, dict[str, object]]:
        params: dict[str, object] = {
            "platform": platform,
            "shop_id": shop_id,
            "order_keyword": order_keyword.strip(),
            "order_keyword_like": f"%{order_keyword.strip()}%",
            "tracking_no": tracking_no.strip(),
        }
        where_clauses: list[str] = [self._finance_test_shop_exclusion("f")]

        if from_date is not None:
            params["from_date"] = from_date
            where_clauses.append("f.shipped_date >= :from_date")

        if to_date is not None:
            params["to_date"] = to_date
            where_clauses.append("f.shipped_date <= :to_date")

        if platform:
            where_clauses.append("f.platform = :platform")

        if shop_id:
            where_clauses.append("f.shop_id = :shop_id")

        if warehouse_id is not None:
            params["warehouse_id"] = int(warehouse_id)
            where_clauses.append("f.warehouse_id = :warehouse_id")

        if shipping_provider_id is not None:
            params["shipping_provider_id"] = int(shipping_provider_id)
            where_clauses.append("f.shipping_provider_id = :shipping_provider_id")

        if order_keyword.strip():
            where_clauses.append(
                """
                (
                  f.order_ref ILIKE :order_keyword_like
                  OR f.tracking_no ILIKE :order_keyword_like
                )
                """
            )

        if tracking_no.strip():
            where_clauses.append("f.tracking_no = :tracking_no")

        return "\n        AND ".join(where_clauses), params

    async def _summary(self, params: dict[str, object]) -> dict[str, object]:
        sql = text(
            f"""
            SELECT
              COUNT(*) AS shipment_count,
              COALESCE(SUM(COALESCE(f.cost_estimated, 0)), 0) AS estimated_shipping_cost
            FROM finance_shipping_cost_lines f
            WHERE {self._base_where("f")}
            """
        )
        row = (await self.session.execute(sql, params)).mappings().one()
        return {
            "shipment_count": int(row["shipment_count"] or 0),
            "estimated_shipping_cost": to_decimal(row["estimated_shipping_cost"]),
            "billed_shipping_cost": to_decimal(0),
            "cost_diff": to_decimal(0),
            "adjusted_cost": to_decimal(0),
        }

    async def _daily(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            WITH day_dim AS (
              SELECT generate_series(:from_date, :to_date, interval '1 day')::date AS day
            ),
            estimated AS (
              SELECT
                f.shipped_date AS day,
                COUNT(*) AS shipment_count,
                COALESCE(SUM(COALESCE(f.cost_estimated, 0)), 0) AS estimated_shipping_cost
              FROM finance_shipping_cost_lines f
              WHERE {self._base_where("f")}
              GROUP BY f.shipped_date
            )
            SELECT
              d.day,
              COALESCE(e.shipment_count, 0) AS shipment_count,
              COALESCE(e.estimated_shipping_cost, 0) AS estimated_shipping_cost
            FROM day_dim d
            LEFT JOIN estimated e ON e.day = d.day
            ORDER BY d.day ASC
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "day": row["day"],
                "shipment_count": int(row["shipment_count"] or 0),
                "estimated_shipping_cost": to_decimal(row["estimated_shipping_cost"]),
                "billed_shipping_cost": to_decimal(0),
                "cost_diff": to_decimal(0),
                "adjusted_cost": to_decimal(0),
            }
            for row in rows
        ]

    async def _by_provider(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            SELECT
              f.shipping_provider_id,
              MAX(f.shipping_provider_code) AS shipping_provider_code,
              MAX(f.shipping_provider_name) AS shipping_provider_name,
              COUNT(*) AS shipment_count,
              COALESCE(SUM(COALESCE(f.cost_estimated, 0)), 0) AS estimated_shipping_cost
            FROM finance_shipping_cost_lines f
            WHERE {self._base_where("f")}
            GROUP BY f.shipping_provider_id
            ORDER BY estimated_shipping_cost DESC, shipping_provider_id ASC
            LIMIT 100
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "shipping_provider_id": int(row["shipping_provider_id"])
                if row["shipping_provider_id"] is not None
                else None,
                "shipping_provider_code": row["shipping_provider_code"],
                "shipping_provider_name": row["shipping_provider_name"],
                "shipment_count": int(row["shipment_count"] or 0),
                "estimated_shipping_cost": to_decimal(row["estimated_shipping_cost"]),
                "billed_shipping_cost": to_decimal(0),
            }
            for row in rows
        ]

    async def _by_shop(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            SELECT
              f.platform,
              f.shop_id,
              MAX(f.shop_name) AS shop_name,
              COUNT(*) AS shipment_count,
              COALESCE(SUM(COALESCE(f.cost_estimated, 0)), 0) AS estimated_shipping_cost
            FROM finance_shipping_cost_lines f
            WHERE {self._base_where("f")}
            GROUP BY f.platform, f.shop_id
            ORDER BY estimated_shipping_cost DESC, f.platform ASC, f.shop_id ASC
            LIMIT 100
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "platform": str(row["platform"]),
                "shop_id": str(row["shop_id"]),
                "shop_name": row["shop_name"],
                "shipment_count": int(row["shipment_count"] or 0),
                "estimated_shipping_cost": to_decimal(row["estimated_shipping_cost"]),
                "billed_shipping_cost": to_decimal(0),
            }
            for row in rows
        ]
