# app/api/routers/shipping_reports_routes_by_province.py
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.shipping_reports_helpers import (
    build_where_clause,
    clean_opt_str,
    parse_date_param,
)
from app.api.routers.shipping_reports_schemas import (
    ShippingByProvinceResponse,
    ShippingByProvinceRow,
)


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
        district: Optional[str] = Query(None),
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
        district_clean = clean_opt_str(district)

        where_sql, params = build_where_clause(
            from_dt=from_dt,
            to_dt=to_dt,
            platform=platform_clean,
            shop_id=shop_id_clean,
            carrier_code=carrier_code_clean,
            province=province_clean,
            warehouse_id=warehouse_id,
            city=city_clean,
            district=district_clean,
            include_province_filter=True,
        )

        sql = text(
            f"""
            SELECT
              meta->>'dest_province' AS province,
              COUNT(*) AS ship_cnt,
              COALESCE(SUM(cost_estimated), 0)::float AS total_cost,
              CASE WHEN COUNT(*) > 0
                   THEN COALESCE(AVG(cost_estimated), 0)::float
                   ELSE 0.0 END AS avg_cost
            FROM shipping_records
            WHERE {where_sql}
            GROUP BY meta->>'dest_province'
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
