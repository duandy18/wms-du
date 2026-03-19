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
    carrier_bill_item_id: int,
    weight_diff_kg: object | None,
    cost_diff: object | None,
) -> None:
    existing_id = (
        await session.execute(
            text(
                """
                SELECT id
                FROM shipping_record_reconciliations
                WHERE carrier_bill_item_id = :carrier_bill_item_id
                   OR (
                        :shipping_record_id IS NOT NULL
                        AND shipping_record_id = :shipping_record_id
                   )
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {
                "carrier_bill_item_id": carrier_bill_item_id,
                "shipping_record_id": shipping_record_id,
            },
        )
    ).scalar()

    params = {
        "status": status,
        "carrier_code": carrier_code,
        "tracking_no": tracking_no,
        "shipping_record_id": shipping_record_id,
        "carrier_bill_item_id": carrier_bill_item_id,
        "weight_diff_kg": weight_diff_kg,
        "cost_diff": cost_diff,
    }

    if existing_id is not None:
        await session.execute(
            text(
                """
                UPDATE shipping_record_reconciliations
                SET
                    status = :status,
                    carrier_code = :carrier_code,
                    tracking_no = :tracking_no,
                    shipping_record_id = :shipping_record_id,
                    carrier_bill_item_id = :carrier_bill_item_id,
                    weight_diff_kg = :weight_diff_kg,
                    cost_diff = :cost_diff,
                    adjust_amount = NULL,
                    approved_reason_code = NULL,
                    approved_reason_text = NULL,
                    approved_at = NULL
                WHERE id = :id
                """
            ),
            {
                **params,
                "id": int(existing_id),
            },
        )
        return

    await session.execute(
        text(
            """
            INSERT INTO shipping_record_reconciliations (
                status,
                carrier_code,
                tracking_no,
                shipping_record_id,
                carrier_bill_item_id,
                weight_diff_kg,
                cost_diff,
                adjust_amount,
                approved_reason_code,
                approved_reason_text,
                approved_at
            )
            VALUES (
                :status,
                :carrier_code,
                :tracking_no,
                :shipping_record_id,
                :carrier_bill_item_id,
                :weight_diff_kg,
                :cost_diff,
                NULL,
                NULL,
                NULL,
                NULL
            )
            """
        ),
        params,
    )


async def delete_shipping_record_reconciliation(
    session: AsyncSession,
    *,
    shipping_record_id: int | None = None,
    carrier_bill_item_id: int | None = None,
) -> None:
    if shipping_record_id is None and carrier_bill_item_id is None:
        return

    where_parts: list[str] = []
    params: dict[str, Any] = {}

    if shipping_record_id is not None:
        where_parts.append("shipping_record_id = :shipping_record_id")
        params["shipping_record_id"] = shipping_record_id

    if carrier_bill_item_id is not None:
        where_parts.append("carrier_bill_item_id = :carrier_bill_item_id")
        params["carrier_bill_item_id"] = carrier_bill_item_id

    where_sql = " OR ".join(where_parts)

    await session.execute(
        text(
            f"""
            DELETE FROM shipping_record_reconciliations
            WHERE {where_sql}
            """
        ),
        params,
    )


async def delete_archived_shipping_record_reconciliations_by_carrier(
    session: AsyncSession,
    *,
    carrier_code: str,
) -> None:
    await session.execute(
        text(
            """
            DELETE FROM shipping_record_reconciliations r
            WHERE upper(r.carrier_code) = upper(:carrier_code)
              AND EXISTS (
                  SELECT 1
                  FROM shipping_bill_reconciliation_histories h
                  WHERE h.carrier_bill_item_id = r.carrier_bill_item_id
              )
            """
        ),
        {"carrier_code": carrier_code},
    )


async def get_shipping_record_reconciliation_by_id(
    session: AsyncSession,
    *,
    reconciliation_id: int,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT
                    id,
                    status,
                    carrier_code,
                    tracking_no,
                    shipping_record_id,
                    carrier_bill_item_id,
                    weight_diff_kg,
                    cost_diff,
                    adjust_amount,
                    approved_reason_code,
                    approved_reason_text,
                    approved_at,
                    created_at
                FROM shipping_record_reconciliations
                WHERE id = :reconciliation_id
                """
            ),
            {"reconciliation_id": reconciliation_id},
        )
    ).mappings().first()

    return dict(row) if row is not None else None


async def approve_shipping_record_reconciliation(
    session: AsyncSession,
    *,
    reconciliation_id: int,
    approved_reason_code: str,
    adjust_amount: object,
    approved_reason_text: str | None,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                UPDATE shipping_record_reconciliations
                SET
                    approved_reason_code = :approved_reason_code,
                    adjust_amount = :adjust_amount,
                    approved_reason_text = :approved_reason_text,
                    approved_at = now()
                WHERE id = :reconciliation_id
                RETURNING
                    id,
                    status,
                    carrier_code,
                    tracking_no,
                    shipping_record_id,
                    carrier_bill_item_id,
                    weight_diff_kg,
                    cost_diff,
                    adjust_amount,
                    approved_reason_code,
                    approved_reason_text,
                    approved_at,
                    created_at
                """
            ),
            {
                "reconciliation_id": reconciliation_id,
                "approved_reason_code": approved_reason_code,
                "adjust_amount": adjust_amount,
                "approved_reason_text": approved_reason_text,
            },
        )
    ).mappings().first()

    return dict(row) if row is not None else None


async def delete_shipping_record_reconciliation_by_id(
    session: AsyncSession,
    *,
    reconciliation_id: int,
) -> None:
    await session.execute(
        text(
            """
            DELETE FROM shipping_record_reconciliations
            WHERE id = :reconciliation_id
            """
        ),
        {"reconciliation_id": reconciliation_id},
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
            r.approved_reason_code,
            r.approved_reason_text,
            r.approved_at,
            r.created_at
        FROM shipping_record_reconciliations r
        WHERE {where_sql}
        ORDER BY r.created_at DESC, r.id DESC
        LIMIT :limit OFFSET :offset
        """
    )

    rows = (await session.execute(query_sql, params)).mappings().all()
    return total, [dict(r) for r in rows]
