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
    reconcile_status: Optional[str] = None,
    min_cost_diff: Optional[float] = None,
    min_weight_diff: Optional[float] = None,
    include_province_filter: bool = True,
) -> tuple[str, dict[str, Any]]:
    """
    根据给定参数构造 WHERE 子句和绑定参数。
    所有条件都是“有就加、没就不出现”，避免 asyncpg 的类型歧义问题。

    ✅ PROD-only（Shipping 报表口径，store_id 级别门禁）：
    - 仅排除测试店铺（platform_test_shops.code='DEFAULT'）
    - 门禁锚点使用 store_id（与 platform_test_shops 的 not-null 约束一致）：
        shipping_records(platform, shop_id) -> stores.id -> platform_test_shops.store_id
    - 不做“测试商品/订单级”过滤（避免跨表锚点不稳导致 500）
    """
    conditions: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    # ----------------- PROD-only 护栏：排除测试店铺（store_id 级别） -----------------
    conditions.append(
        """
        NOT EXISTS (
          SELECT 1
            FROM stores s
            JOIN platform_test_shops pts
              ON pts.store_id = s.id
             AND pts.code = 'DEFAULT'
           WHERE upper(s.platform) = upper(shipping_records.platform)
             AND btrim(CAST(s.shop_id AS text)) = btrim(CAST(shipping_records.shop_id AS text))
        )
        """.strip()
    )

    # ----------------- 业务过滤条件（有就加） -----------------
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
    if reconcile_status:
        conditions.append("reconcile_status = :reconcile_status")
        params["reconcile_status"] = reconcile_status
    if min_cost_diff is not None:
        conditions.append("ABS(cost_diff) >= :min_cost_diff")
        params["min_cost_diff"] = min_cost_diff
    if min_weight_diff is not None:
        conditions.append("ABS(weight_diff_kg) >= :min_weight_diff")
        params["min_weight_diff"] = min_weight_diff

    where_sql = " AND ".join(conditions)
    return where_sql, params
