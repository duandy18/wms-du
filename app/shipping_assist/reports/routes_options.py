# app/shipping_assist/reports/routes_options.py
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.shipping_assist.reports.contracts import ShippingReportFilterOptions
from app.shipping_assist.reports.helpers import build_where_clause, parse_date_param


def register(router: APIRouter) -> None:
    @router.get(
        "/shipping-assist/reports/options",
        response_model=ShippingReportFilterOptions,
    )
    async def shipping_reports_options(
        from_date: Optional[str] = Query(None),
        to_date: Optional[str] = Query(None),
        warehouse_id: Optional[int] = Query(None),
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> ShippingReportFilterOptions:
        from_dt = parse_date_param(from_date)
        to_dt = parse_date_param(to_date)

        where_sql, params = build_where_clause(
            from_dt=from_dt,
            to_dt=to_dt,
            platform=None,
            shop_id=None,
            shipping_provider_code=None,
            province=None,
            warehouse_id=warehouse_id,
            city=None,
        )

        sql_platform_shop = text(
            f"""
            SELECT DISTINCT sr.platform, sr.shop_id
            FROM shipping_records sr
            WHERE {where_sql}
            """
        )
        res_ps = await session.execute(sql_platform_shop, params)
        ps_rows = res_ps.mappings().all()

        platforms_set: set[str] = set()
        shop_ids_set: set[str] = set()
        for r in ps_rows:
            plat = str(r["platform"])
            shop = str(r["shop_id"])
            platforms_set.add(plat)
            shop_ids_set.add(shop)

        sql_province = text(
            f"""
            SELECT DISTINCT sr.dest_province AS province
            FROM shipping_records sr
            WHERE {where_sql}
              AND sr.dest_province IS NOT NULL
            """
        )
        res_prov = await session.execute(sql_province, params)
        provinces = [str(r["province"]) for r in res_prov.mappings().all() if r["province"]]

        sql_city = text(
            f"""
            SELECT DISTINCT sr.dest_city AS city
            FROM shipping_records sr
            WHERE {where_sql}
              AND sr.dest_city IS NOT NULL
            """
        )
        res_city = await session.execute(sql_city, params)
        cities = [str(r["city"]) for r in res_city.mappings().all() if r["city"]]

        return ShippingReportFilterOptions(
            platforms=sorted(platforms_set),
            shop_ids=sorted(shop_ids_set),
            provinces=sorted(set(provinces)),
            cities=sorted(set(cities)),
        )
