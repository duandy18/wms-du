# app/shipping_assist/billing/repository_cost_analysis.py
#
# 职责：
# - 承载 TMS / Billing（快递账单）成本分析只读聚合查询
# - 口径仅基于 carrier_bill_items
# - 时间维度固定按天（business_time::date）
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _clean_opt_str(value: str | None) -> str | None:
    return (value or "").strip() or None


def _build_where_clause(
    *,
    shipping_provider_code: str | None,
    start_date: date | None,
    end_date: date | None,
) -> tuple[str, dict[str, Any]]:
    conditions: list[str] = ["cbi.business_time IS NOT NULL"]
    params: dict[str, Any] = {}

    shipping_provider_code_clean = _clean_opt_str(shipping_provider_code)
    if shipping_provider_code_clean:
        conditions.append("upper(cbi.shipping_provider_code) = upper(:shipping_provider_code)")
        params["shipping_provider_code"] = shipping_provider_code_clean

    if start_date is not None:
        conditions.append("cbi.business_time::date >= :start_date")
        params["start_date"] = start_date

    if end_date is not None:
        conditions.append("cbi.business_time::date <= :end_date")
        params["end_date"] = end_date

    return " AND ".join(conditions), params


async def get_billing_cost_analysis(
    session: AsyncSession,
    *,
    shipping_provider_code: str | None,
    start_date: date | None,
    end_date: date | None,
) -> dict[str, object]:
    where_sql, params = _build_where_clause(
        shipping_provider_code=shipping_provider_code,
        start_date=start_date,
        end_date=end_date,
    )

    by_carrier_sql = text(
        f"""
        SELECT
          cbi.shipping_provider_code,
          COUNT(*) AS ticket_count,
          COALESCE(
            SUM(
              COALESCE(
                cbi.total_amount,
                COALESCE(cbi.freight_amount, 0) + COALESCE(cbi.surcharge_amount, 0)
              )
            ),
            0
          )::float AS total_cost
        FROM carrier_bill_items cbi
        WHERE {where_sql}
        GROUP BY cbi.shipping_provider_code
        ORDER BY total_cost DESC, cbi.shipping_provider_code NULLS LAST
        """
    )

    by_time_sql = text(
        f"""
        SELECT
          to_char(cbi.business_time::date, 'YYYY-MM-DD') AS bucket,
          COUNT(*) AS ticket_count,
          COALESCE(
            SUM(
              COALESCE(
                cbi.total_amount,
                COALESCE(cbi.freight_amount, 0) + COALESCE(cbi.surcharge_amount, 0)
              )
            ),
            0
          )::float AS total_cost
        FROM carrier_bill_items cbi
        WHERE {where_sql}
        GROUP BY bucket
        ORDER BY bucket ASC
        """
    )

    by_carrier_rows = [
        {
            "shipping_provider_code": row.get("shipping_provider_code"),
            "ticket_count": int(row["ticket_count"] or 0),
            "total_cost": float(row["total_cost"] or 0.0),
        }
        for row in (await session.execute(by_carrier_sql, params)).mappings().all()
    ]

    by_time_rows = [
        {
            "bucket": str(row["bucket"]),
            "ticket_count": int(row["ticket_count"] or 0),
            "total_cost": float(row["total_cost"] or 0.0),
        }
        for row in (await session.execute(by_time_sql, params)).mappings().all()
    ]

    summary = {
        "ticket_count": sum(int(row["ticket_count"]) for row in by_carrier_rows),
        "total_cost": float(sum(float(row["total_cost"]) for row in by_carrier_rows)),
    }

    return {
        "summary": summary,
        "by_carrier": by_carrier_rows,
        "by_time": by_time_rows,
    }
