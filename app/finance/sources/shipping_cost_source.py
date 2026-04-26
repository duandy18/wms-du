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
        store_code: str = "",
    ) -> dict[str, Any]:
        params = {
            "from_date": from_date,
            "to_date": to_date,
            "platform": platform,
            "store_code": store_code,
        }
        summary = await self._summary(params)
        daily = await self._daily(params)
        by_provider = await self._by_provider(params)
        by_store = await self._by_store(params)
        return {
            "summary": summary,
            "daily": daily,
            "by_carrier": by_provider,
            "by_store": by_store,
        }

    async def fetch_shipping_ledger(
        self,
        *,
        from_date: date | None,
        to_date: date | None,
        platform: str = "",
        store_code: str = "",
        warehouse_id: int | None = None,
        shipping_provider_id: int | None = None,
        order_keyword: str = "",
        tracking_no: str = "",
    ) -> dict[str, Any]:
        where_sql, params = self._build_ledger_filters(
            from_date=from_date,
            to_date=to_date,
            platform=platform,
            store_code=store_code,
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
              store_code,
              store_name,
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
              freight_estimated,
              surcharge_estimated,
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
        store_code: str = "",
        warehouse_id: int | None = None,
        shipping_provider_id: int | None = None,
    ) -> dict[str, Any]:
        where_sql, params = self._build_ledger_filters(
            from_date=from_date,
            to_date=to_date,
            platform=platform,
            store_code=store_code,
            warehouse_id=warehouse_id,
            shipping_provider_id=shipping_provider_id,
            order_keyword="",
            tracking_no="",
        )

        stores = (
            await self.session.execute(
                text(
                    f"""
                    SELECT
                      platform,
                      store_code,
                      MAX(store_name) AS store_name
                    FROM finance_shipping_cost_lines f
                    WHERE {where_sql}
                    GROUP BY platform, store_code
                    ORDER BY platform ASC, store_code ASC
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
            "stores": [dict(row) for row in stores],
            "warehouses": [dict(row) for row in warehouses],
            "providers": [dict(row) for row in providers],
        }

    def _base_where(self, alias: str = "f") -> str:
        return f"""
        {alias}.shipped_date BETWEEN :from_date AND :to_date
        AND (:platform = '' OR {alias}.platform = :platform)
        AND (:store_code = '' OR {alias}.store_code = :store_code)
        AND NOT EXISTS (
          SELECT 1
            FROM platform_test_stores pts
           WHERE pts.code = 'DEFAULT'
             AND upper(pts.platform) = upper({alias}.platform)
             AND btrim(CAST(pts.store_code AS text)) = btrim(CAST({alias}.store_code AS text))
        )
        """

    def _finance_test_store_exclusion(self, alias: str = "f") -> str:
        return f"""
        NOT EXISTS (
          SELECT 1
            FROM platform_test_stores pts
           WHERE pts.code = 'DEFAULT'
             AND upper(pts.platform) = upper({alias}.platform)
             AND btrim(CAST(pts.store_code AS text)) = btrim(CAST({alias}.store_code AS text))
        )
        """

    def _build_ledger_filters(
        self,
        *,
        from_date: date | None,
        to_date: date | None,
        platform: str,
        store_code: str,
        warehouse_id: int | None,
        shipping_provider_id: int | None,
        order_keyword: str,
        tracking_no: str,
    ) -> tuple[str, dict[str, object]]:
        params: dict[str, object] = {
            "platform": platform,
            "store_code": store_code,
            "order_keyword": order_keyword.strip(),
            "order_keyword_like": f"%{order_keyword.strip()}%",
            "tracking_no": tracking_no.strip(),
        }
        where_clauses: list[str] = [self._finance_test_store_exclusion("f")]

        if from_date is not None:
            params["from_date"] = from_date
            where_clauses.append("f.shipped_date >= :from_date")

        if to_date is not None:
            params["to_date"] = to_date
            where_clauses.append("f.shipped_date <= :to_date")

        if platform:
            where_clauses.append("f.platform = :platform")

        if store_code:
            where_clauses.append("f.store_code = :store_code")

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

    async def _by_store(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            SELECT
              f.platform,
              f.store_code,
              MAX(f.store_name) AS store_name,
              COUNT(*) AS shipment_count,
              COALESCE(SUM(COALESCE(f.cost_estimated, 0)), 0) AS estimated_shipping_cost
            FROM finance_shipping_cost_lines f
            WHERE {self._base_where("f")}
            GROUP BY f.platform, f.store_code
            ORDER BY estimated_shipping_cost DESC, f.platform ASC, f.store_code ASC
            LIMIT 100
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "platform": str(row["platform"]),
                "store_code": str(row["store_code"]),
                "store_name": row["store_name"],
                "shipment_count": int(row["shipment_count"] or 0),
                "estimated_shipping_cost": to_decimal(row["estimated_shipping_cost"]),
                "billed_shipping_cost": to_decimal(0),
            }
            for row in rows
        ]
