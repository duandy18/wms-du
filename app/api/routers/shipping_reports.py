# app/api/routers/shipping_reports.py
from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session

router = APIRouter(tags=["shipping-reports"])


# ----------------- Schemas -----------------


class ShippingByCarrierRow(BaseModel):
    carrier_code: Optional[str] = None
    carrier_name: Optional[str] = None
    ship_cnt: int
    total_cost: float
    avg_cost: float


class ShippingByCarrierResponse(BaseModel):
    ok: bool = True
    rows: List[ShippingByCarrierRow]


class ShippingByProvinceRow(BaseModel):
    province: Optional[str] = None
    ship_cnt: int
    total_cost: float
    avg_cost: float


class ShippingByProvinceResponse(BaseModel):
    ok: bool = True
    rows: List[ShippingByProvinceRow]


class ShippingByShopRow(BaseModel):
    platform: str
    shop_id: str
    ship_cnt: int
    total_cost: float
    avg_cost: float


class ShippingByShopResponse(BaseModel):
    ok: bool = True
    rows: List[ShippingByShopRow]


class ShippingByWarehouseRow(BaseModel):
    warehouse_id: Optional[int] = None
    ship_cnt: int
    total_cost: float
    avg_cost: float


class ShippingByWarehouseResponse(BaseModel):
    ok: bool = True
    rows: List[ShippingByWarehouseRow]


class ShippingDailyRow(BaseModel):
    stat_date: str  # YYYY-MM-DD
    ship_cnt: int
    total_cost: float
    avg_cost: float


class ShippingDailyResponse(BaseModel):
    ok: bool = True
    rows: List[ShippingDailyRow]


class ShippingListRow(BaseModel):
    id: int
    order_ref: str
    platform: str
    shop_id: str
    warehouse_id: Optional[int] = None

    trace_id: Optional[str] = None

    carrier_code: Optional[str] = None
    carrier_name: Optional[str] = None

    gross_weight_kg: Optional[float] = None
    packaging_weight_kg: Optional[float] = None
    cost_estimated: Optional[float] = None

    status: Optional[str] = None
    meta: Optional[dict] = None
    created_at: str


class ShippingListResponse(BaseModel):
    ok: bool = True
    rows: List[ShippingListRow]
    total: int


class ShippingReportFilterOptions(BaseModel):
    platforms: List[str]
    shop_ids: List[str]
    provinces: List[str]
    cities: List[str]


# ----------------- Helpers -----------------


def _parse_date_param(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    return date.fromisoformat(v)


def _build_where_clause(
    *,
    from_dt: Optional[date],
    to_dt: Optional[date],
    platform: Optional[str],
    shop_id: Optional[str],
    carrier_code: Optional[str],
    province: Optional[str],
    warehouse_id: Optional[int],
    city: Optional[str] = None,
    district: Optional[str] = None,
    include_province_filter: bool = True,
) -> tuple[str, dict]:
    """
    根据给定参数构造 WHERE 子句和绑定参数。
    所有条件都是“有就加、没就不出现”，避免 asyncpg 的类型歧义问题。
    """
    conditions: List[str] = ["1=1"]
    params: dict[str, Any] = {}

    if from_dt is not None:
        conditions.append("created_at::date >= :from_date")
        params["from_date"] = from_dt
    if to_dt is not None:
        conditions.append("created_at::date <= :to_date")
        params["to_date"] = to_dt
    if platform:
        conditions.append("platform = :platform")
        params["platform"] = platform
    if shop_id:
        conditions.append("shop_id = :shop_id")
        params["shop_id"] = shop_id
    if carrier_code:
        conditions.append("carrier_code = :carrier_code")
        params["carrier_code"] = carrier_code
    if include_province_filter and province:
        conditions.append("meta->>'dest_province' = :province")
        params["province"] = province
    if city:
        conditions.append("meta->>'dest_city' = :city")
        params["city"] = city
    if district:
        conditions.append("meta->>'dest_district' = :district")
        params["district"] = district
    if warehouse_id is not None:
        conditions.append("warehouse_id = :warehouse_id")
        params["warehouse_id"] = warehouse_id

    where_sql = " AND ".join(conditions)
    return where_sql, params


# ----------------- by-carrier -----------------


@router.get(
    "/shipping-reports/by-carrier",
    response_model=ShippingByCarrierResponse,
)
async def shipping_reports_by_carrier(
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
    current_user: Any = Depends(get_current_user),
):
    from_dt = _parse_date_param(from_date)
    to_dt = _parse_date_param(to_date)
    platform = (platform or "").strip() or None
    shop_id = (shop_id or "").strip() or None
    carrier_code = (carrier_code or "").strip() or None
    province = (province or "").strip() or None
    city = (city or "").strip() or None
    district = (district or "").strip() or None

    where_sql, params = _build_where_clause(
        from_dt=from_dt,
        to_dt=to_dt,
        platform=platform,
        shop_id=shop_id,
        carrier_code=carrier_code,
        province=province,
        warehouse_id=warehouse_id,
        city=city,
        district=district,
        include_province_filter=True,
    )

    sql = text(
        f"""
        SELECT
          carrier_code,
          carrier_name,
          COUNT(*) AS ship_cnt,
          COALESCE(SUM(cost_estimated), 0)::float AS total_cost,
          CASE WHEN COUNT(*) > 0
               THEN COALESCE(AVG(cost_estimated), 0)::float
               ELSE 0.0 END AS avg_cost
        FROM shipping_records
        WHERE {where_sql}
        GROUP BY carrier_code, carrier_name
        ORDER BY total_cost DESC, carrier_code NULLS LAST
        """
    )

    result = await session.execute(sql, params)
    rows = result.mappings().all()

    return ShippingByCarrierResponse(
        ok=True,
        rows=[
            ShippingByCarrierRow(
                carrier_code=r.get("carrier_code"),
                carrier_name=r.get("carrier_name"),
                ship_cnt=int(r["ship_cnt"] or 0),
                total_cost=float(r["total_cost"] or 0.0),
                avg_cost=float(r["avg_cost"] or 0.0),
            )
            for r in rows
        ],
    )


# ----------------- by-province -----------------


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
    current_user: Any = Depends(get_current_user),
):
    from_dt = _parse_date_param(from_date)
    to_dt = _parse_date_param(to_date)
    platform = (platform or "").strip() or None
    shop_id = (shop_id or "").strip() or None
    carrier_code = (carrier_code or "").strip() or None
    province = (province or "").strip() or None
    city = (city or "").strip() or None
    district = (district or "").strip() or None

    where_sql, params = _build_where_clause(
        from_dt=from_dt,
        to_dt=to_dt,
        platform=platform,
        shop_id=shop_id,
        carrier_code=carrier_code,
        province=province,
        warehouse_id=warehouse_id,
        city=city,
        district=district,
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


# ----------------- by-shop -----------------


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
    current_user: Any = Depends(get_current_user),
):
    from_dt = _parse_date_param(from_date)
    to_dt = _parse_date_param(to_date)
    platform = (platform or "").strip() or None
    shop_id_clean = (shop_id or "").strip() or None
    carrier_code = (carrier_code or "").strip() or None
    province = (province or "").strip() or None
    city = (city or "").strip() or None
    district = (district or "").strip() or None

    where_sql, params = _build_where_clause(
        from_dt=from_dt,
        to_dt=to_dt,
        platform=platform,
        shop_id=shop_id_clean,
        carrier_code=carrier_code,
        province=province,
        warehouse_id=warehouse_id,
        city=city,
        district=district,
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


# ----------------- by-warehouse -----------------


@router.get(
    "/shipping-reports/by-warehouse",
    response_model=ShippingByWarehouseResponse,
)
async def shipping_reports_by_warehouse(
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
    current_user: Any = Depends(get_current_user),
):
    from_dt = _parse_date_param(from_date)
    to_dt = _parse_date_param(to_date)
    platform = (platform or "").strip() or None
    shop_id = (shop_id or "").strip() or None
    carrier_code = (carrier_code or "").strip() or None
    province = (province or "").strip() or None
    city = (city or "").strip() or None
    district = (district or "").strip() or None

    where_sql, params = _build_where_clause(
        from_dt=from_dt,
        to_dt=to_dt,
        platform=platform,
        shop_id=shop_id,
        carrier_code=carrier_code,
        province=province,
        warehouse_id=warehouse_id,
        city=city,
        district=district,
        include_province_filter=True,
    )

    sql = text(
        f"""
        SELECT
          warehouse_id,
          COUNT(*) AS ship_cnt,
          COALESCE(SUM(cost_estimated), 0)::float AS total_cost,
          CASE WHEN COUNT(*) > 0
               THEN COALESCE(AVG(cost_estimated), 0)::float
               ELSE 0.0 END AS avg_cost
        FROM shipping_records
        WHERE {where_sql}
        GROUP BY warehouse_id
        ORDER BY total_cost DESC, warehouse_id NULLS LAST
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


# ----------------- daily -----------------


@router.get(
    "/shipping-reports/daily",
    response_model=ShippingDailyResponse,
)
async def shipping_reports_daily(
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
    current_user: Any = Depends(get_current_user),
):
    from_dt = _parse_date_param(from_date)
    to_dt = _parse_date_param(to_date)
    platform = (platform or "").strip() or None
    shop_id = (shop_id or "").strip() or None
    carrier_code = (carrier_code or "").strip() or None
    province = (province or "").strip() or None
    city = (city or "").strip() or None
    district = (district or "").strip() or None

    where_sql, params = _build_where_clause(
        from_dt=from_dt,
        to_dt=to_dt,
        platform=platform,
        shop_id=shop_id,
        carrier_code=carrier_code,
        province=province,
        warehouse_id=warehouse_id,
        city=city,
        district=district,
        include_province_filter=True,
    )

    sql = text(
        f"""
        SELECT
          created_at::date AS stat_date,
          COUNT(*) AS ship_cnt,
          COALESCE(SUM(cost_estimated), 0)::float AS total_cost,
          CASE WHEN COUNT(*) > 0
               THEN COALESCE(AVG(cost_estimated), 0)::float
               ELSE 0.0 END AS avg_cost
        FROM shipping_records
        WHERE {where_sql}
        GROUP BY stat_date
        ORDER BY stat_date ASC
        """
    )

    result = await session.execute(sql, params)
    rows = result.mappings().all()

    return ShippingDailyResponse(
        ok=True,
        rows=[
            ShippingDailyRow(
                stat_date=r["stat_date"].isoformat(),
                ship_cnt=int(r["ship_cnt"] or 0),
                total_cost=float(r["total_cost"] or 0.0),
                avg_cost=float(r["avg_cost"] or 0.0),
            )
            for r in rows
        ],
    )


# ----------------- list（明细列表） -----------------


@router.get(
    "/shipping-reports/list",
    response_model=ShippingListResponse,
)
async def shipping_reports_list(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    shop_id: Optional[str] = Query(None),
    carrier_code: Optional[str] = Query(None),
    province: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    warehouse_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: Any = Depends(get_current_user),
):
    """
    发货明细列表（带过滤条件 + 分页）。
    """
    from_dt = _parse_date_param(from_date)
    to_dt = _parse_date_param(to_date)
    platform = (platform or "").strip() or None
    shop_id = (shop_id or "").strip() or None
    carrier_code = (carrier_code or "").strip() or None
    province = (province or "").strip() or None
    city = (city or "").strip() or None
    district = (district or "").strip() or None

    where_sql, params = _build_where_clause(
        from_dt=from_dt,
        to_dt=to_dt,
        platform=platform,
        shop_id=shop_id,
        carrier_code=carrier_code,
        province=province,
        warehouse_id=warehouse_id,
        city=city,
        district=district,
        include_province_filter=True,
    )
    params["limit"] = limit
    params["offset"] = offset

    # 总数
    count_sql = text(f"SELECT COUNT(*) FROM shipping_records WHERE {where_sql}")
    count_params = {k: v for k, v in params.items() if k not in {"limit", "offset"}}
    total_result = await session.execute(count_sql, count_params)
    total = int(total_result.scalar() or 0)

    sql = text(
        f"""
        SELECT
          id,
          order_ref,
          platform,
          shop_id,
          warehouse_id,
          trace_id,
          carrier_code,
          carrier_name,
          gross_weight_kg,
          packaging_weight_kg,
          cost_estimated,
          status,
          meta,
          created_at
        FROM shipping_records
        WHERE {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT :limit OFFSET :offset
        """
    )

    result = await session.execute(sql, params)
    rows = result.mappings().all()

    return ShippingListResponse(
        ok=True,
        rows=[
            ShippingListRow(
                id=int(r["id"]),
                order_ref=str(r["order_ref"]),
                platform=str(r["platform"]),
                shop_id=str(r["shop_id"]),
                warehouse_id=r.get("warehouse_id"),
                trace_id=r.get("trace_id"),
                carrier_code=r.get("carrier_code"),
                carrier_name=r.get("carrier_name"),
                gross_weight_kg=(
                    float(r["gross_weight_kg"]) if r["gross_weight_kg"] is not None else None
                ),
                packaging_weight_kg=(
                    float(r["packaging_weight_kg"])
                    if r["packaging_weight_kg"] is not None
                    else None
                ),
                cost_estimated=(
                    float(r["cost_estimated"]) if r["cost_estimated"] is not None else None
                ),
                status=r.get("status"),
                meta=r.get("meta"),
                created_at=r["created_at"].isoformat(),
            )
            for r in rows
        ],
        total=total,
    )


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
    current_user: Any = Depends(get_current_user),
):
    """
    发货报表下拉选项：
    - 平台列表（platform）
    - 店铺 ID 列表（shop_id）
    - 省份列表（meta.dest_province）
    - 城市列表（meta.dest_city）
    只统计当前日期范围内 shipping_records 出现过的值。
    """
    from_dt = _parse_date_param(from_date)
    to_dt = _parse_date_param(to_date)

    where_sql, params = _build_where_clause(
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
