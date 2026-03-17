# app/tms/billing/repository_items.py
"""
【拆分说明】

本文件从原 repository.py 中拆分而来。

职责：
- carrier_bill_items（账单明细表）相关操作

设计原则：
- import_batch_id 是明细所属批次的唯一内部主链
- import_batch_no / carrier_code 为展示与检索字段，不承担系统内部主驱动职责

拆分原因：
- 原 repository.py 同时承担批次、明细、对账结果、发货记录辅助查询四类职责，已出现膨胀
- 本文件只负责“账单明细”，避免跨职责污染

重要约束：
- 不得在本文件中操作 carrier_bill_import_batches
- 不得在本文件中操作 shipping_record_reconciliations
- 不得在本文件中承载 shipping_records 的辅助查询
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _json_dumps(obj: dict[str, object]) -> str:
    return json.dumps(obj, ensure_ascii=False)


async def delete_carrier_bill_items_by_batch(
    session: AsyncSession,
    *,
    import_batch_id: int,
) -> None:
    sql = text(
        """
        DELETE FROM carrier_bill_items
        WHERE import_batch_id = :import_batch_id
        """
    )
    await session.execute(sql, {"import_batch_id": import_batch_id})


async def insert_carrier_bill_items(
    session: AsyncSession,
    *,
    import_batch_id: int,
    rows: list[dict[str, object]],
    carrier_code: str,
    import_batch_no: str,
    bill_month: str | None,
) -> int:
    sql = text(
        """
        INSERT INTO carrier_bill_items (
            import_batch_id,
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
            :import_batch_id,
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
                "import_batch_id": import_batch_id,
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
    import_batch_id: int | None,
    import_batch_no: str | None,
    carrier_code: str | None,
    tracking_no: str | None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, Any]]]:
    where_parts = ["1=1"]
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if import_batch_id is not None:
        where_parts.append("cbi.import_batch_id = :import_batch_id")
        params["import_batch_id"] = import_batch_id

    if import_batch_no:
        where_parts.append("cbi.import_batch_no = :import_batch_no")
        params["import_batch_no"] = import_batch_no

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
        JOIN carrier_bill_import_batches b
          ON b.id = cbi.import_batch_id
        WHERE {where_sql}
        """
    )
    count_params = {k: v for k, v in params.items() if k not in {"limit", "offset"}}
    total = int((await session.execute(count_sql, count_params)).scalar() or 0)

    query_sql = text(
        f"""
        SELECT
            cbi.id,
            cbi.import_batch_id,
            cbi.import_batch_no,
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
        JOIN carrier_bill_import_batches b
          ON b.id = cbi.import_batch_id
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
    import_batch_id: int,
) -> list[dict[str, Any]]:
    sql = text(
        """
        SELECT
            id,
            import_batch_id,
            tracking_no,
            business_time,
            billing_weight_kg,
            freight_amount,
            surcharge_amount
        FROM carrier_bill_items
        WHERE import_batch_id = :import_batch_id
        ORDER BY id ASC
        """
    )
    rows = (
        await session.execute(
            sql,
            {
                "import_batch_id": import_batch_id,
            },
        )
    ).mappings().all()
    return [dict(r) for r in rows]
