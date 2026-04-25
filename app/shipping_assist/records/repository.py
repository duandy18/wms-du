# app/shipping_assist/records/repository.py
#
# 分拆说明：
# - 本文件承载 TMS / Records（物流台帐）只读查询；
# - shipping_records 是由发货执行流程生成的运输事实台帐；
# - Records 域仅提供列表与导出，不混入状态域 / 对账域字段。
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_SELECT_SHIPPING_LEDGER_BASE = """
SELECT
  id,
  order_ref,
  warehouse_id,
  shipping_provider_id,
  carrier_code,
  carrier_name,
  tracking_no,
  freight_estimated,
  surcharge_estimated,
  cost_estimated,
  gross_weight_kg,
  length_cm,
  width_cm,
  height_cm,
  sender,
  dest_province,
  dest_city,
  created_at
FROM shipping_records
"""


def _clean_opt_str(value: str | None) -> str | None:
    return (value or "").strip() or None


def _build_where_clause(
    *,
    from_date: date | None,
    to_date: date | None,
    order_ref: str | None,
    tracking_no: str | None,
    carrier_code: str | None,
    shipping_provider_id: int | None,
    province: str | None,
    city: str | None,
    warehouse_id: int | None,
) -> tuple[str, dict[str, Any]]:
    conditions: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if from_date is not None:
        conditions.append("created_at::date >= :from_date")
        params["from_date"] = from_date
    if to_date is not None:
        conditions.append("created_at::date <= :to_date")
        params["to_date"] = to_date

    order_ref_clean = _clean_opt_str(order_ref)
    if order_ref_clean:
        conditions.append("order_ref = :order_ref")
        params["order_ref"] = order_ref_clean

    tracking_no_clean = _clean_opt_str(tracking_no)
    if tracking_no_clean:
        conditions.append("tracking_no = :tracking_no")
        params["tracking_no"] = tracking_no_clean

    carrier_code_clean = _clean_opt_str(carrier_code)
    if carrier_code_clean:
        conditions.append("carrier_code = :carrier_code")
        params["carrier_code"] = carrier_code_clean

    if shipping_provider_id is not None:
        conditions.append("shipping_provider_id = :shipping_provider_id")
        params["shipping_provider_id"] = int(shipping_provider_id)

    province_clean = _clean_opt_str(province)
    if province_clean:
        conditions.append("dest_province = :province")
        params["province"] = province_clean

    city_clean = _clean_opt_str(city)
    if city_clean:
        conditions.append("dest_city = :city")
        params["city"] = city_clean

    if warehouse_id is not None:
        conditions.append("warehouse_id = :warehouse_id")
        params["warehouse_id"] = warehouse_id

    return " AND ".join(conditions), params


async def list_shipping_ledger(
    session: AsyncSession,
    *,
    from_date: date | None,
    to_date: date | None,
    order_ref: str | None,
    tracking_no: str | None,
    carrier_code: str | None,
    shipping_provider_id: int | None,
    province: str | None,
    city: str | None,
    warehouse_id: int | None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, object]]]:
    where_sql, params = _build_where_clause(
        from_date=from_date,
        to_date=to_date,
        order_ref=order_ref,
        tracking_no=tracking_no,
        carrier_code=carrier_code,
        shipping_provider_id=shipping_provider_id,
        province=province,
        city=city,
        warehouse_id=warehouse_id,
    )

    count_sql = text(
        f"""
        SELECT COUNT(*)
        FROM shipping_records
        WHERE {where_sql}
        """
    )
    count_result = await session.execute(count_sql, params)
    total = int(count_result.scalar() or 0)

    query_params = dict(params)
    query_params["limit"] = limit
    query_params["offset"] = offset

    query_sql = text(
        f"""
        {_SELECT_SHIPPING_LEDGER_BASE}
        WHERE {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT :limit OFFSET :offset
        """
    )
    rows = (await session.execute(query_sql, query_params)).mappings().all()
    return total, [dict(r) for r in rows]


async def export_shipping_ledger_rows(
    session: AsyncSession,
    *,
    from_date: date | None,
    to_date: date | None,
    order_ref: str | None,
    tracking_no: str | None,
    carrier_code: str | None,
    shipping_provider_id: int | None,
    province: str | None,
    city: str | None,
    warehouse_id: int | None,
) -> list[dict[str, object]]:
    where_sql, params = _build_where_clause(
        from_date=from_date,
        to_date=to_date,
        order_ref=order_ref,
        tracking_no=tracking_no,
        carrier_code=carrier_code,
        shipping_provider_id=shipping_provider_id,
        province=province,
        city=city,
        warehouse_id=warehouse_id,
    )

    sql = text(
        f"""
        {_SELECT_SHIPPING_LEDGER_BASE}
        WHERE {where_sql}
        ORDER BY created_at DESC, id DESC
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows]
