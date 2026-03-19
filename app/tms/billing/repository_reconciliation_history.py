# app/tms/billing/repository_reconciliation_history.py
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def insert_shipping_bill_reconciliation_history(
    session: AsyncSession,
    *,
    carrier_bill_item_id: int,
    shipping_record_id: int | None,
    carrier_code: str,
    tracking_no: str,
    result_status: str,
    weight_diff_kg: object | None,
    cost_diff: object | None,
    adjust_amount: object | None,
    approved_reason_code: str,
    approved_reason_text: str | None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO shipping_bill_reconciliation_histories (
                carrier_bill_item_id,
                shipping_record_id,
                carrier_code,
                tracking_no,
                result_status,
                weight_diff_kg,
                cost_diff,
                adjust_amount,
                approved_reason_code,
                approved_reason_text,
                archived_at
            )
            VALUES (
                :carrier_bill_item_id,
                :shipping_record_id,
                :carrier_code,
                :tracking_no,
                :result_status,
                :weight_diff_kg,
                :cost_diff,
                :adjust_amount,
                :approved_reason_code,
                :approved_reason_text,
                now()
            )
            ON CONFLICT (carrier_bill_item_id) DO NOTHING
            """
        ),
        {
            "carrier_bill_item_id": carrier_bill_item_id,
            "shipping_record_id": shipping_record_id,
            "carrier_code": carrier_code,
            "tracking_no": tracking_no,
            "result_status": result_status,
            "weight_diff_kg": weight_diff_kg,
            "cost_diff": cost_diff,
            "adjust_amount": adjust_amount,
            "approved_reason_code": approved_reason_code,
            "approved_reason_text": approved_reason_text,
        },
    )


async def delete_shipping_bill_reconciliation_history(
    session: AsyncSession,
    *,
    carrier_bill_item_id: int,
) -> None:
    await session.execute(
        text(
            """
            DELETE FROM shipping_bill_reconciliation_histories
            WHERE carrier_bill_item_id = :carrier_bill_item_id
            """
        ),
        {"carrier_bill_item_id": carrier_bill_item_id},
    )


async def get_shipping_bill_reconciliation_history_exists(
    session: AsyncSession,
    *,
    carrier_bill_item_id: int,
) -> bool:
    row = await session.execute(
        text(
            """
            SELECT 1
            FROM shipping_bill_reconciliation_histories
            WHERE carrier_bill_item_id = :carrier_bill_item_id
            LIMIT 1
            """
        ),
        {"carrier_bill_item_id": carrier_bill_item_id},
    )
    return row.scalar() is not None


async def list_shipping_bill_reconciliation_histories(
    session: AsyncSession,
    *,
    carrier_code: str | None,
    tracking_no: str | None,
    result_status: str | None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, Any]]]:
    where_parts = ["1=1"]
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if carrier_code:
        where_parts.append("upper(h.carrier_code) = upper(:carrier_code)")
        params["carrier_code"] = carrier_code

    if tracking_no:
        where_parts.append("h.tracking_no = :tracking_no")
        params["tracking_no"] = tracking_no

    if result_status:
        where_parts.append("h.result_status = :result_status")
        params["result_status"] = result_status

    where_sql = " AND ".join(where_parts)

    count_sql = text(
        f"""
        SELECT COUNT(*)
        FROM shipping_bill_reconciliation_histories h
        WHERE {where_sql}
        """
    )
    count_params = {k: v for k, v in params.items() if k not in {"limit", "offset"}}
    total = int((await session.execute(count_sql, count_params)).scalar() or 0)

    query_sql = text(
        f"""
        SELECT
            h.id,
            h.carrier_bill_item_id,
            h.shipping_record_id,
            h.carrier_code,
            h.tracking_no,
            h.result_status,
            h.weight_diff_kg,
            h.cost_diff,
            h.adjust_amount,
            h.approved_reason_code,
            h.approved_reason_text,
            h.archived_at
        FROM shipping_bill_reconciliation_histories h
        WHERE {where_sql}
        ORDER BY h.archived_at DESC, h.id DESC
        LIMIT :limit OFFSET :offset
        """
    )

    rows = (await session.execute(query_sql, params)).mappings().all()
    return total, [dict(r) for r in rows]
