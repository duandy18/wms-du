# app/services/stock_service_batches.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import normalize_optional_batch_code


async def ensure_batch_dict(
    *,
    session: AsyncSession,
    warehouse_id: int,
    item_id: int,
    batch_code: Optional[str],
    production_date: Optional[date],
    expiry_date: Optional[date],
    created_at: datetime,
) -> None:
    """
    若不存在批次主档则创建；若已存在，则不更新日期（避免覆盖历史业务档案）。

    注意：batches 主档当前 schema：
      - batch_code NOT NULL
      - 唯一约束：(item_id, warehouse_id, batch_code)

    ✅ 主线 B：与“无批次=NULL 槽位”世界观对齐
    - 非批次商品的槽位 batch_code 为 NULL，但 batches 主档不应为其创建记录
    - 因此：batch_code 归一后若为 None（None/空串/'None'），直接跳过
    - 严禁把 None 写成字符串 'None'
    """
    bc = normalize_optional_batch_code(batch_code)
    if bc is None:
        return

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
            "i": int(item_id),
            "w": int(warehouse_id),
            "code": bc,
            "prod": production_date,
            "exp": expiry_date,
            "created_at": created_at,
        },
    )
