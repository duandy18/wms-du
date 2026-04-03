# app/tms/reports/routes_by_province.py
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.tms.reports.contracts import ShippingByProvinceResponse, ShippingByProvinceRow
from app.tms.reports.helpers import build_where_clause, clean_opt_str, parse_date_param


def register(router: APIRouter) -> None:
    @router.get(
        "/shipping-reports/by-province",
        response_model=ShippingByProvinceResponse,
    )
    async def shipping_reports_by_province(
        from_date: Optional[str] = Query(None),
        to_date: Optional[str] = Query(None),
        platform: Optional[str] = Query(None),
        shop_id: Optional[str] = Query(None),
        carrier_code: Optional[str] = Query(None),
        province: Optional[str] = Query(None),
        city: Optional[str] = Query(None),
        warehouse_id: Optional[int] = Query(None),
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> ShippingByProvinceResponse:
        from_dt = parse_date_param(from_date)
        to_dt = parse_date_param(to_date)
        platform_clean = clean_opt_str(platform)
        shop_id_clean = clean_opt_str(shop_id)
        carrier_code_clean = clean_opt_str(carrier_code)
        province_clean = clean_opt_str(province)
        city_clean = clean_opt_str(city)

        where_sql, params = build_where_clause(
            from_dt=from_dt,
            to_dt=to_dt,
            platform=platform_clean,
            shop_id=shop_id_clean,
            carrier_code=carrier_code_clean,
            province=province_clean,
            warehouse_id=warehouse_id,
            city=city_clean,
        )

        sql = text(
            f"""
            SELECT
              sr.dest_province AS province,
              COUNT(*) AS ship_cnt,
              COALESCE(SUM(sr.cost_estimated), 0)::float AS total_cost,
              CASE WHEN COUNT(*) > 0
                   THEN COALESCE(AVG(sr.cost_estimated), 0)::float
                   ELSE 0.0 END AS avg_cost
            FROM shipping_records sr
            WHERE {where_sql}
            GROUP BY sr.dest_province
            ORDER BY avg_cost DESC, province NULLS LAST
            """
        )

        result = await session.execute(sql, params)
        rows = result.mappings().all()

        return ShippingByProvinceResponse(
            ok=True,
            rows=[
                ShippingByProvinceRow(
                    province=r.get("province"),
                    ship_cnt=int(r["ship_cnt"] or 0),
                    total_cost=float(r["total_cost"] or 0.0),
                    avg_cost=float(r["avg_cost"] or 0.0),
                )
                for r in rows
            ],
        )
