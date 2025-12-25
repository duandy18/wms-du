# app/services/stock_service_batches.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_batch_dict(
    *,
    session: AsyncSession,
    warehouse_id: int,
    item_id: int,
    batch_code: str,
    production_date: Optional[date],
    expiry_date: Optional[date],
    created_at: datetime,
) -> None:
    """
    若不存在批次主档则创建；若已存在，则不更新日期（避免覆盖历史业务档案）。

    注意：按 v2/v3 统一模型，批次维度为 (item_id, warehouse_id, batch_code)。
    """
    await session.execute(
        text(
            """
            INSERT INTO batches (
                item_id,
                warehouse_id,
                batch_code,
                production_date,
                expiry_date,
                created_at
            )
            VALUES (
                :i, :w, :code, :prod, :exp, :created_at
            )
            ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
            """
        ),
        {
            "i": item_id,
            "w": int(warehouse_id),
            "code": batch_code,
            "prod": production_date,
            "exp": expiry_date,
            "created_at": created_at,
        },
    )
