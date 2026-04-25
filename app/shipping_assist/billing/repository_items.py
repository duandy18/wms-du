# app/shipping_assist/billing/repository_items.py
"""
职责：
- carrier_bill_items（账单明细表）相关操作

设计原则：
- carrier_code + tracking_no 为业务唯一键（幂等导入核心）
- 不再依赖 import_batch_id
- 不再保留 import_batch_no
- 导入采用 UPSERT（ON CONFLICT），实现幂等增量补录
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _json_dumps(obj: dict[str, object]) -> str:
    return json.dumps(obj, ensure_ascii=False)


async def insert_carrier_bill_items(
    session: AsyncSession,
    *,
    rows: list[dict[str, object]],
    carrier_code: str,
    bill_month: str | None,
) -> int:
    sql = text(
        """
        INSERT INTO carrier_bill_items (
            carrier_code,
            bill_month,
            tracking_no,
            business_time,
            destination_province,
            destination_city,
            billing_weight_kg,
            freight_amount,
            surcharge_amount,
            total_amount,
            settlement_object,
            order_customer,
            sender_name,
            network_name,
            size_text,
            parent_customer,
            raw_payload
        )
        VALUES (
            :carrier_code,
            :bill_month,
            :tracking_no,
            :business_time,
            :destination_province,
            :destination_city,
            :billing_weight_kg,
            :freight_amount,
            :surcharge_amount,
            :total_amount,
            :settlement_object,
            :order_customer,
            :sender_name,
            :network_name,
            :size_text,
            :parent_customer,
            CAST(:raw_payload AS jsonb)
        )
        ON CONFLICT (carrier_code, tracking_no)
        DO UPDATE SET
            bill_month = EXCLUDED.bill_month,

            business_time = COALESCE(EXCLUDED.business_time, carrier_bill_items.business_time),
            destination_province = COALESCE(EXCLUDED.destination_province, carrier_bill_items.destination_province),
            destination_city = COALESCE(EXCLUDED.destination_city, carrier_bill_items.destination_city),

            billing_weight_kg = COALESCE(EXCLUDED.billing_weight_kg, carrier_bill_items.billing_weight_kg),
            freight_amount = COALESCE(EXCLUDED.freight_amount, carrier_bill_items.freight_amount),
            surcharge_amount = COALESCE(EXCLUDED.surcharge_amount, carrier_bill_items.surcharge_amount),
            total_amount = COALESCE(EXCLUDED.total_amount, carrier_bill_items.total_amount),

            settlement_object = COALESCE(EXCLUDED.settlement_object, carrier_bill_items.settlement_object),
            order_customer = COALESCE(EXCLUDED.order_customer, carrier_bill_items.order_customer),
            sender_name = COALESCE(EXCLUDED.sender_name, carrier_bill_items.sender_name),
            network_name = COALESCE(EXCLUDED.network_name, carrier_bill_items.network_name),
            size_text = COALESCE(EXCLUDED.size_text, carrier_bill_items.size_text),
            parent_customer = COALESCE(EXCLUDED.parent_customer, carrier_bill_items.parent_customer),

            raw_payload = EXCLUDED.raw_payload,
            created_at = now()

        WHERE
            carrier_bill_items.bill_month IS DISTINCT FROM EXCLUDED.bill_month
         OR carrier_bill_items.raw_payload IS DISTINCT FROM EXCLUDED.raw_payload
         OR carrier_bill_items.billing_weight_kg IS DISTINCT FROM EXCLUDED.billing_weight_kg
         OR carrier_bill_items.freight_amount IS DISTINCT FROM EXCLUDED.freight_amount
         OR carrier_bill_items.surcharge_amount IS DISTINCT FROM EXCLUDED.surcharge_amount
         OR carrier_bill_items.total_amount IS DISTINCT FROM EXCLUDED.total_amount
         OR carrier_bill_items.destination_province IS DISTINCT FROM EXCLUDED.destination_province
         OR carrier_bill_items.destination_city IS DISTINCT FROM EXCLUDED.destination_city
         OR carrier_bill_items.business_time IS DISTINCT FROM EXCLUDED.business_time
         OR carrier_bill_items.settlement_object IS DISTINCT FROM EXCLUDED.settlement_object
         OR carrier_bill_items.order_customer IS DISTINCT FROM EXCLUDED.order_customer
         OR carrier_bill_items.sender_name IS DISTINCT FROM EXCLUDED.sender_name
         OR carrier_bill_items.network_name IS DISTINCT FROM EXCLUDED.network_name
         OR carrier_bill_items.size_text IS DISTINCT FROM EXCLUDED.size_text
         OR carrier_bill_items.parent_customer IS DISTINCT FROM EXCLUDED.parent_customer;
        """
    )

    affected = 0

    for row in rows:
        await session.execute(
            sql,
            {
                "carrier_code": carrier_code,
                "bill_month": bill_month,
                "tracking_no": row.get("tracking_no"),
                "business_time": row.get("business_time"),
                "destination_province": row.get("destination_province"),
                "destination_city": row.get("destination_city"),
                "billing_weight_kg": row.get("billing_weight_kg"),
                "freight_amount": row.get("freight_amount"),
                "surcharge_amount": row.get("surcharge_amount"),
                "total_amount": row.get("total_amount"),
                "settlement_object": row.get("settlement_object"),
                "order_customer": row.get("order_customer"),
                "sender_name": row.get("sender_name"),
                "network_name": row.get("network_name"),
                "size_text": row.get("size_text"),
                "parent_customer": row.get("parent_customer"),
                "raw_payload": _json_dumps(dict(row.get("raw_payload") or {})),
            },
        )
        affected += 1

    return affected


async def list_carrier_bill_items(
    session: AsyncSession,
    *,
    carrier_code: str | None,
    tracking_no: str | None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, Any]]]:
    where_parts = ["1=1"]
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if carrier_code:
        where_parts.append("upper(cbi.carrier_code) = upper(:carrier_code)")
        params["carrier_code"] = carrier_code

    if tracking_no:
        where_parts.append("cbi.tracking_no = :tracking_no")
        params["tracking_no"] = tracking_no

    where_sql = " AND ".join(where_parts)

    count_sql = text(
        f"""
        SELECT COUNT(*)
        FROM carrier_bill_items cbi
        WHERE {where_sql}
        """
    )
    count_params = {k: v for k, v in params.items() if k not in {"limit", "offset"}}
    total = int((await session.execute(count_sql, count_params)).scalar() or 0)

    query_sql = text(
        f"""
        SELECT
            cbi.id,
            cbi.carrier_code,
            cbi.bill_month,
            cbi.tracking_no,
            cbi.business_time,
            cbi.destination_province,
            cbi.destination_city,
            cbi.billing_weight_kg,
            cbi.freight_amount,
            cbi.surcharge_amount,
            cbi.total_amount,
            cbi.settlement_object,
            cbi.order_customer,
            cbi.sender_name,
            cbi.network_name,
            cbi.size_text,
            cbi.parent_customer,
            cbi.raw_payload,
            cbi.created_at
        FROM carrier_bill_items cbi
        WHERE {where_sql}
        ORDER BY cbi.created_at DESC, cbi.id DESC
        LIMIT :limit OFFSET :offset
        """
    )

    rows = (await session.execute(query_sql, params)).mappings().all()
    return total, [dict(r) for r in rows]


async def list_carrier_bill_items_for_reconcile(
    session: AsyncSession,
    *,
    carrier_code: str,
) -> list[dict[str, Any]]:
    sql = text(
        """
        SELECT
            b.id,
            b.tracking_no,
            b.business_time,
            b.billing_weight_kg,
            b.freight_amount,
            b.surcharge_amount
        FROM carrier_bill_items b
        WHERE upper(b.carrier_code) = upper(:carrier_code)
          AND NOT EXISTS (
              SELECT 1
              FROM shipping_bill_reconciliation_histories h
              WHERE h.carrier_bill_item_id = b.id
          )
        """
    )

    rows = (
        await session.execute(
            sql,
            {"carrier_code": carrier_code},
        )
    ).mappings().all()

    return [dict(r) for r in rows]
