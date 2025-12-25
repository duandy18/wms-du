# app/api/routers/shipping_reports_routes_options.py
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.shipping_reports_helpers import build_where_clause, parse_date_param
from app.api.routers.shipping_reports_schemas import ShippingReportFilterOptions


def register(router: APIRouter) -> None:
    # ----------------- options（下拉选项） -----------------
    @router.get(
        "/shipping-reports/options",
        response_model=ShippingReportFilterOptions,
    )
    async def shipping_reports_options(
        from_date: Optional[str] = Query(None),
        to_date: Optional[str] = Query(None),
        warehouse_id: Optional[int] = Query(None),
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> ShippingReportFilterOptions:
        """
        发货报表下拉选项：
        - 平台列表（platform）
        - 店铺 ID 列表（shop_id）
        - 省份列表（meta.dest_province）
        - 城市列表（meta.dest_city）
        只统计当前日期范围内 shipping_records 出现过的值。
        """
        from_dt = parse_date_param(from_date)
        to_dt = parse_date_param(to_date)

        where_sql, params = build_where_clause(
            from_dt=from_dt,
            to_dt=to_dt,
            platform=None,
            shop_id=None,
            carrier_code=None,
            province=None,
            warehouse_id=warehouse_id,
            city=None,
            district=None,
            include_province_filter=False,
        )

        # 平台 / 店铺
        sql_platform_shop = text(
            f"""
            SELECT DISTINCT platform, shop_id
            FROM shipping_records
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

        # 省份
        sql_province = text(
            f"""
            SELECT DISTINCT meta->>'dest_province' AS province
            FROM shipping_records
            WHERE {where_sql}
              AND meta->>'dest_province' IS NOT NULL
            """
        )
        res_prov = await session.execute(sql_province, params)
        provinces = [str(r["province"]) for r in res_prov.mappings().all() if r["province"]]

        # 城市
        sql_city = text(
            f"""
            SELECT DISTINCT meta->>'dest_city' AS city
            FROM shipping_records
            WHERE {where_sql}
              AND meta->>'dest_city' IS NOT NULL
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
