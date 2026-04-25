# app/shipping_assist/billing/repository_records.py
"""
【拆分说明】

本文件从原 repository.py 中拆分而来。

职责：
- shipping_records（发货记录表）在账单对账场景下的辅助读取

设计原则：
- 本文件只提供“当前正式对账主链所需的发货记录读取能力”
- 这里的查询服务于 billing 域，但不负责 shipping_records 域本身的写操作

拆分原因：
- 原 repository.py 同时承担批次、明细、对账结果、发货记录辅助查询四类职责，已出现膨胀
- 本文件只负责“对账辅助查询”，避免跨职责污染

重要约束：
- 不得在本文件中操作 carrier_bill_import_batches
- 不得在本文件中操作 carrier_bill_items
- 不得在本文件中操作 shipping_record_reconciliations
- 不得在本文件中承担 shipping_records 的写入职责
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession


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
