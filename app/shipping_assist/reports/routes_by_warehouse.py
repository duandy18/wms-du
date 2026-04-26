# app/shipping_assist/reports/routes_by_warehouse.py
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.shipping_assist.reports.contracts import ShippingByWarehouseResponse, ShippingByWarehouseRow
from app.shipping_assist.reports.helpers import build_where_clause, clean_opt_str, parse_date_param


def register(router: APIRouter) -> None:
    @router.get(
        "/shipping-assist/reports/by-warehouse",
        response_model=ShippingByWarehouseResponse,
    )
    async def shipping_reports_by_warehouse(
        from_date: Optional[str] = Query(None),
        to_date: Optional[str] = Query(None),
        platform: Optional[str] = Query(None),
        store_code: Optional[str] = Query(None),
        shipping_provider_code: Optional[str] = Query(None),
        province: Optional[str] = Query(None),
        city: Optional[str] = Query(None),
        warehouse_id: Optional[int] = Query(None),
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> ShippingByWarehouseResponse:
        from_dt = parse_date_param(from_date)
        to_dt = parse_date_param(to_date)
        platform_clean = clean_opt_str(platform)
        store_code_clean = clean_opt_str(store_code)
        shipping_provider_code_clean = clean_opt_str(shipping_provider_code)
        province_clean = clean_opt_str(province)
        city_clean = clean_opt_str(city)

        where_sql, params = build_where_clause(
            from_dt=from_dt,
            to_dt=to_dt,
            platform=platform_clean,
            store_code=store_code_clean,
            shipping_provider_code=shipping_provider_code_clean,
            province=province_clean,
            warehouse_id=warehouse_id,
            city=city_clean,
        )

        sql = text(
            f"""
            SELECT
              sr.warehouse_id,
              COUNT(*) AS ship_cnt,
              COALESCE(SUM(sr.cost_estimated), 0)::float AS total_cost,
              CASE WHEN COUNT(*) > 0
                   THEN COALESCE(AVG(sr.cost_estimated), 0)::float
                   ELSE 0.0 END AS avg_cost
            FROM shipping_records sr
            WHERE {where_sql}
            GROUP BY sr.warehouse_id
            ORDER BY total_cost DESC, sr.warehouse_id NULLS LAST
            """
        )

        result = await session.execute(sql, params)
        rows = result.mappings().all()

        return ShippingByWarehouseResponse(
            ok=True,
            rows=[
                ShippingByWarehouseRow(
                    warehouse_id=r.get("warehouse_id"),
                    ship_cnt=int(r["ship_cnt"] or 0),
                    total_cost=float(r["total_cost"] or 0.0),
                    avg_cost=float(r["avg_cost"] or 0.0),
                )
                for r in rows
            ],
        )
