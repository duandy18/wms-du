# app/tms/reports/helpers.py
#
# 分拆说明：
# - 本文件承载 TMS / Reports（运输报表）查询过滤 helper；
# - 当前报表口径统一基于 shipping_records sr；
# - Reports 域只保留聚合分析与筛选项；
# - 不再使用旧 meta / district / reconcile_status 语义。
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


def parse_bool_param(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    v = value.strip().lower()
    if not v:
        return None
    if v in {"1", "true", "t", "yes", "y"}:
        return True
    if v in {"0", "false", "f", "no", "n"}:
        return False
    raise ValueError("invalid boolean param")


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
) -> tuple[str, dict[str, Any]]:
    """
    基于 shipping_records sr 拼装 WHERE。
    """
    conditions: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    conditions.append(
        """
        NOT EXISTS (
          SELECT 1
            FROM stores s
            JOIN platform_test_shops pts
              ON pts.store_id = s.id
             AND pts.code = 'DEFAULT'
           WHERE upper(s.platform) = upper(sr.platform)
             AND btrim(CAST(s.shop_id AS text)) = btrim(CAST(sr.shop_id AS text))
        )
        """.strip()
    )

    if from_dt is not None:
        conditions.append("sr.created_at::date >= :from_date")
        params["from_date"] = from_dt
    if to_dt is not None:
        conditions.append("sr.created_at::date <= :to_date")
        params["to_date"] = to_dt
    if platform:
        conditions.append("sr.platform = :platform")
        params["platform"] = platform
    if shop_id:
        conditions.append("sr.shop_id = :shop_id")
        params["shop_id"] = shop_id
    if carrier_code:
        conditions.append("sr.carrier_code = :carrier_code")
        params["carrier_code"] = carrier_code
    if province:
        conditions.append("sr.dest_province = :province")
        params["province"] = province
    if city:
        conditions.append("sr.dest_city = :city")
        params["city"] = city
    if warehouse_id is not None:
        conditions.append("sr.warehouse_id = :warehouse_id")
        params["warehouse_id"] = warehouse_id

    where_sql = " AND ".join(conditions)
    return where_sql, params
