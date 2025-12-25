# app/api/routers/shipping_reports_routes_by_shop.py
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
from app.api.routers.shipping_reports_schemas import ShippingByShopResponse, ShippingByShopRow


def register(router: APIRouter) -> None:
    @router.get(
        "/shipping-reports/by-shop",
        response_model=ShippingByShopResponse,
    )
    async def shipping_reports_by_shop(
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
    ) -> ShippingByShopResponse:
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
              platform,
              shop_id,
              COUNT(*) AS ship_cnt,
              COALESCE(SUM(cost_estimated), 0)::float AS total_cost,
              CASE WHEN COUNT(*) > 0
                   THEN COALESCE(AVG(cost_estimated), 0)::float
                   ELSE 0.0 END AS avg_cost
            FROM shipping_records
            WHERE {where_sql}
            GROUP BY platform, shop_id
            ORDER BY total_cost DESC, platform, shop_id
            """
        )

        result = await session.execute(sql, params)
        rows = result.mappings().all()

        return ShippingByShopResponse(
            ok=True,
            rows=[
                ShippingByShopRow(
                    platform=str(r["platform"]),
                    shop_id=str(r["shop_id"]),
                    ship_cnt=int(r["ship_cnt"] or 0),
                    total_cost=float(r["total_cost"] or 0.0),
                    avg_cost=float(r["avg_cost"] or 0.0),
                )
                for r in rows
            ],
        )
