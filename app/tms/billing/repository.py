# app/tms/billing/repository.py
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession


def _json_dumps(obj: dict[str, object]) -> str:
    return json.dumps(obj, ensure_ascii=False)


async def insert_carrier_bill_items(
    session: AsyncSession,
    *,
    rows: list[dict[str, object]],
    carrier_code: str,
    import_batch_no: str,
    bill_month: str | None,
) -> int:
    sql = text(
        """
        INSERT INTO carrier_bill_items (
            import_batch_no,
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
            :import_batch_no,
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
        """
    )

    inserted = 0
    for row in rows:
        await session.execute(
            sql,
            {
                "import_batch_no": import_batch_no,
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
        inserted += 1

    return inserted


async def list_carrier_bill_items(
    session: AsyncSession,
    *,
    import_batch_no: str | None,
    carrier_code: str | None,
    tracking_no: str | None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, Any]]]:
    where_parts = ["1=1"]
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if import_batch_no:
        where_parts.append("import_batch_no = :import_batch_no")
        params["import_batch_no"] = import_batch_no

    if carrier_code:
        where_parts.append("upper(carrier_code) = upper(:carrier_code)")
        params["carrier_code"] = carrier_code

    if tracking_no:
        where_parts.append("tracking_no = :tracking_no")
        params["tracking_no"] = tracking_no

    where_sql = " AND ".join(where_parts)

    count_sql = text(f"SELECT COUNT(*) FROM carrier_bill_items WHERE {where_sql}")
    count_params = {k: v for k, v in params.items() if k not in {"limit", "offset"}}
    total = int((await session.execute(count_sql, count_params)).scalar() or 0)

    query_sql = text(
        f"""
        SELECT
            id,
            import_batch_no,
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
            raw_payload,
            created_at
        FROM carrier_bill_items
        WHERE {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT :limit OFFSET :offset
        """
    )
    rows = (await session.execute(query_sql, params)).mappings().all()
    return total, [dict(r) for r in rows]


async def list_carrier_bill_items_for_reconcile(
    session: AsyncSession,
    *,
    import_batch_no: str,
    carrier_code: str,
) -> list[dict[str, Any]]:
    sql = text(
        """
        SELECT
            id,
            tracking_no,
            billing_weight_kg,
            freight_amount,
            surcharge_amount
        FROM carrier_bill_items
        WHERE import_batch_no = :import_batch_no
          AND upper(carrier_code) = upper(:carrier_code)
        ORDER BY id ASC
        """
    )
    rows = (
        await session.execute(
            sql,
            {
                "import_batch_no": import_batch_no,
                "carrier_code": carrier_code,
            },
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def list_shipping_records_for_reconcile(
    session: AsyncSession,
    *,
    carrier_code: str,
    tracking_nos: list[str],
) -> list[dict[str, Any]]:
    if not tracking_nos:
        return []

    sql = (
        text(
            """
            SELECT
                id,
                tracking_no,
                gross_weight_kg,
                cost_estimated
            FROM shipping_records
            WHERE upper(carrier_code) = upper(:carrier_code)
              AND tracking_no IN :tracking_nos
            """
        ).bindparams(bindparam("tracking_nos", expanding=True))
    )

    rows = (
        await session.execute(
            sql,
            {
                "carrier_code": carrier_code,
                "tracking_nos": tracking_nos,
            },
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def upsert_shipping_record_reconciliation(
    session: AsyncSession,
    *,
    shipping_record_id: int,
    carrier_bill_item_id: int,
    tracking_no: str,
    weight_diff_kg: object | None,
    cost_diff: object | None,
    adjust_amount: object | None,
) -> None:
    sql = text(
        """
        INSERT INTO shipping_record_reconciliations (
            shipping_record_id,
            carrier_bill_item_id,
            tracking_no,
            weight_diff_kg,
            cost_diff,
            adjust_amount
        )
        VALUES (
            :shipping_record_id,
            :carrier_bill_item_id,
            :tracking_no,
            :weight_diff_kg,
            :cost_diff,
            :adjust_amount
        )
        ON CONFLICT (shipping_record_id)
        DO UPDATE SET
            carrier_bill_item_id = EXCLUDED.carrier_bill_item_id,
            tracking_no = EXCLUDED.tracking_no,
            weight_diff_kg = EXCLUDED.weight_diff_kg,
            cost_diff = EXCLUDED.cost_diff,
            adjust_amount = EXCLUDED.adjust_amount
        """
    )
    await session.execute(
        sql,
        {
            "shipping_record_id": shipping_record_id,
            "carrier_bill_item_id": carrier_bill_item_id,
            "tracking_no": tracking_no,
            "weight_diff_kg": weight_diff_kg,
            "cost_diff": cost_diff,
            "adjust_amount": adjust_amount,
        },
    )


async def delete_shipping_record_reconciliation_by_shipping_record_id(
    session: AsyncSession,
    *,
    shipping_record_id: int,
) -> None:
    sql = text(
        """
        DELETE FROM shipping_record_reconciliations
        WHERE shipping_record_id = :shipping_record_id
        """
    )
    await session.execute(sql, {"shipping_record_id": shipping_record_id})
