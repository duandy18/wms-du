# app/tms/billing/repository_batches.py
"""
【拆分说明】

本文件从原 repository.py 中拆分而来。

职责：
- carrier_bill_import_batches（账单导入批次头表）相关操作

设计原则：
- import_batch_id 是 billing 域内部唯一主链
- carrier_code / import_batch_no 是业务键，用于导入幂等、展示与检索
- 批次头表是账单导入与对账流程的聚合根

拆分原因：
- 原 repository.py 同时承担批次、明细、对账结果、发货记录辅助查询四类职责，已出现膨胀
- 本文件只负责“批次头”，避免跨职责污染

重要约束：
- 不得在本文件中操作 carrier_bill_items
- 不得在本文件中操作 shipping_record_reconciliations
- 不得在本文件中承载 shipping_records 的辅助查询
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_carrier_bill_import_batch_by_business_key(
    session: AsyncSession,
    *,
    carrier_code: str,
    import_batch_no: str,
) -> dict[str, Any] | None:
    sql = text(
        """
        SELECT
            id,
            carrier_code,
            import_batch_no,
            bill_month,
            source_filename,
            status,
            row_count,
            success_count,
            error_count,
            imported_at
        FROM carrier_bill_import_batches
        WHERE upper(carrier_code) = upper(:carrier_code)
          AND import_batch_no = :import_batch_no
        LIMIT 1
        """
    )
    row = (
        await session.execute(
            sql,
            {
                "carrier_code": carrier_code,
                "import_batch_no": import_batch_no,
            },
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_carrier_bill_import_batch_by_id(
    session: AsyncSession,
    *,
    import_batch_id: int,
) -> dict[str, Any] | None:
    sql = text(
        """
        SELECT
            id,
            carrier_code,
            import_batch_no,
            bill_month,
            source_filename,
            status,
            row_count,
            success_count,
            error_count,
            imported_at
        FROM carrier_bill_import_batches
        WHERE id = :import_batch_id
        LIMIT 1
        """
    )
    row = (
        await session.execute(
            sql,
            {
                "import_batch_id": import_batch_id,
            },
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def create_carrier_bill_import_batch(
    session: AsyncSession,
    *,
    carrier_code: str,
    import_batch_no: str,
    bill_month: str | None,
    source_filename: str | None,
    row_count: int,
    success_count: int,
    error_count: int,
    status: str = "imported",
) -> int:
    sql = text(
        """
        INSERT INTO carrier_bill_import_batches (
            carrier_code,
            import_batch_no,
            bill_month,
            source_filename,
            status,
            row_count,
            success_count,
            error_count
        )
        VALUES (
            :carrier_code,
            :import_batch_no,
            :bill_month,
            :source_filename,
            :status,
            :row_count,
            :success_count,
            :error_count
        )
        RETURNING id
        """
    )
    result = await session.execute(
        sql,
        {
            "carrier_code": carrier_code,
            "import_batch_no": import_batch_no,
            "bill_month": bill_month,
            "source_filename": source_filename,
            "status": status,
            "row_count": row_count,
            "success_count": success_count,
            "error_count": error_count,
        },
    )
    inserted_id = result.scalar_one()
    return int(inserted_id)


async def update_carrier_bill_import_batch(
    session: AsyncSession,
    *,
    import_batch_id: int,
    bill_month: str | None,
    source_filename: str | None,
    row_count: int,
    success_count: int,
    error_count: int,
    status: str,
) -> None:
    sql = text(
        """
        UPDATE carrier_bill_import_batches
        SET
            bill_month = :bill_month,
            source_filename = :source_filename,
            row_count = :row_count,
            success_count = :success_count,
            error_count = :error_count,
            status = :status,
            imported_at = now()
        WHERE id = :import_batch_id
        """
    )
    await session.execute(
        sql,
        {
            "import_batch_id": import_batch_id,
            "bill_month": bill_month,
            "source_filename": source_filename,
            "row_count": row_count,
            "success_count": success_count,
            "error_count": error_count,
            "status": status,
        },
    )


async def update_carrier_bill_import_batch_status(
    session: AsyncSession,
    *,
    import_batch_id: int,
    status: str,
) -> None:
    sql = text(
        """
        UPDATE carrier_bill_import_batches
        SET status = :status
        WHERE id = :import_batch_id
        """
    )
    await session.execute(
        sql,
        {
            "import_batch_id": import_batch_id,
            "status": status,
        },
    )
