# app/tms/billing/repository_reconciliations.py
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def upsert_shipping_record_reconciliation(
    session: AsyncSession,
    *,
    status: str,
    carrier_code: str,
    tracking_no: str,
    shipping_record_id: int | None,
    carrier_bill_item_id: int | None,
    weight_diff_kg: object | None,
    cost_diff: object | None,
    adjust_amount: object | None,
) -> None:
    if shipping_record_id is not None:
        await session.execute(
            text(
                """
                DELETE FROM shipping_record_reconciliations
                WHERE shipping_record_id = :shipping_record_id
                """
            ),
            {"shipping_record_id": shipping_record_id},
        )

    if carrier_bill_item_id is not None:
        await session.execute(
            text(
                """
                DELETE FROM shipping_record_reconciliations
                WHERE carrier_bill_item_id = :carrier_bill_item_id
                """
            ),
            {"carrier_bill_item_id": carrier_bill_item_id},
        )

    await session.execute(
        text(
            """
            INSERT INTO shipping_record_reconciliations (
                shipping_record_id,
                carrier_bill_item_id,
                tracking_no,
                weight_diff_kg,
                cost_diff,
                adjust_amount,
                status,
                carrier_code
            )
            VALUES (
                :shipping_record_id,
                :carrier_bill_item_id,
                :tracking_no,
                :weight_diff_kg,
                :cost_diff,
                :adjust_amount,
                :status,
                :carrier_code
            )
            """
        ),
        {
            "shipping_record_id": shipping_record_id,
            "carrier_bill_item_id": carrier_bill_item_id,
            "tracking_no": tracking_no,
            "weight_diff_kg": weight_diff_kg,
            "cost_diff": cost_diff,
            "adjust_amount": adjust_amount,
            "status": status,
            "carrier_code": carrier_code,
        },
    )


async def list_shipping_bill_reconciliations(
    session: AsyncSession,
    *,
    carrier_code: str | None,
    tracking_no: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, Any]]]:
    where_parts = ["1=1"]
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if carrier_code:
        where_parts.append("upper(r.carrier_code) = upper(:carrier_code)")
        params["carrier_code"] = carrier_code

    if tracking_no:
        where_parts.append("r.tracking_no = :tracking_no")
        params["tracking_no"] = tracking_no

    if status:
        where_parts.append("r.status = :status")
        params["status"] = status

    where_sql = " AND ".join(where_parts)

    count_sql = text(
        f"""
        SELECT COUNT(*)
        FROM shipping_record_reconciliations r
        LEFT JOIN carrier_bill_items b
          ON b.id = r.carrier_bill_item_id
        LEFT JOIN shipping_records s
          ON s.id = r.shipping_record_id
        WHERE {where_sql}
        """
    )

    count_params = {k: v for k, v in params.items() if k not in {"limit", "offset"}}
    total = int((await session.execute(count_sql, count_params)).scalar() or 0)

    query_sql = text(
        f"""
        SELECT
            r.id AS reconciliation_id,
            r.status,
            r.carrier_code,
            r.tracking_no,
            r.shipping_record_id,
            r.carrier_bill_item_id,
            r.weight_diff_kg,
            r.cost_diff,
            r.adjust_amount,
            r.created_at,

            b.business_time,
            b.destination_province,
            b.destination_city,
            b.billing_weight_kg,
            b.freight_amount,
            b.surcharge_amount,
            b.total_amount,
            COALESCE(b.freight_amount, 0) + COALESCE(b.surcharge_amount, 0) AS bill_cost_real,

            s.gross_weight_kg,
            s.cost_estimated
        FROM shipping_record_reconciliations r
        LEFT JOIN carrier_bill_items b
          ON b.id = r.carrier_bill_item_id
        LEFT JOIN shipping_records s
          ON s.id = r.shipping_record_id
        WHERE {where_sql}
        ORDER BY r.created_at DESC, r.id DESC
        LIMIT :limit OFFSET :offset
        """
    )

    rows = (await session.execute(query_sql, params)).mappings().all()
    return total, [dict(r) for r in rows]


async def get_shipping_bill_reconciliation_detail(
    session: AsyncSession,
    *,
    reconciliation_id: int,
) -> dict[str, Any] | None:
    sql = text(
        """
        SELECT
            r.id AS reconciliation_id,
            r.status,
            r.carrier_code,
            r.tracking_no,
            r.shipping_record_id,
            r.carrier_bill_item_id,
            r.weight_diff_kg,
            r.cost_diff,
            r.adjust_amount,
            r.created_at AS reconciliation_created_at,

            b.id AS bill_id,
            b.carrier_code AS bill_carrier_code,
            b.bill_month,
            b.tracking_no AS bill_tracking_no,
            b.business_time,
            b.destination_province,
            b.destination_city,
            b.billing_weight_kg,
            b.freight_amount,
            b.surcharge_amount,
            b.total_amount,
            b.settlement_object,
            b.order_customer,
            b.sender_name,
            b.network_name,
            b.size_text,
            b.parent_customer,
            b.raw_payload,
            b.created_at AS bill_created_at,

            s.id AS record_id,
            s.order_ref,
            s.platform,
            s.shop_id,
            s.carrier_code AS record_carrier_code,
            s.carrier_name,
            s.tracking_no AS record_tracking_no,
            s.gross_weight_kg,
            s.cost_estimated,
            s.warehouse_id,
            s.shipping_provider_id,
            s.dest_province,
            s.dest_city,
            s.created_at AS record_created_at
        FROM shipping_record_reconciliations r
        LEFT JOIN carrier_bill_items b
          ON b.id = r.carrier_bill_item_id
        LEFT JOIN shipping_records s
          ON s.id = r.shipping_record_id
        WHERE r.id = :reconciliation_id
        """
    )

    row = (
        await session.execute(
            sql,
            {"reconciliation_id": reconciliation_id},
        )
    ).mappings().first()

    return dict(row) if row is not None else None
