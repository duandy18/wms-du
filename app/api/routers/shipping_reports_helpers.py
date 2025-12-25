# app/api/routers/shipping_reports_helpers.py
from __future__ import annotations

from datetime import date
from typing import Any, Optional


def parse_date_param(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    return date.fromisoformat(v)


def clean_opt_str(value: Optional[str]) -> Optional[str]:
    return (value or "").strip() or None


def build_where_clause(
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
) -> tuple[str, dict[str, Any]]:
    """
    根据给定参数构造 WHERE 子句和绑定参数。
    所有条件都是“有就加、没就不出现”，避免 asyncpg 的类型歧义问题。
    """
    conditions: list[str] = ["1=1"]
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
