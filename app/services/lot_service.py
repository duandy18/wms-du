# app/services/lot_service.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import normalize_optional_batch_code


async def ensure_lot_dict(
    *,
    session: AsyncSession,
    warehouse_id: int,
    item_id: int,
    lot_code: Optional[str],
    production_date: Optional[date],
    expiry_date: Optional[date],
    created_at: datetime,
) -> None:
    """
    Phase 4E（真收口）：
    - 禁止写入 legacy 表
    - 若需要批次/lot 主档，统一写入 lots（SUPPLIER lot_code）
    - 非批次商品 lot_code 归一为 None：直接跳过（与 “无 lot 槽位” 对齐）

    说明：
    - 这里不强制更新日期（避免覆盖历史业务档案）
    - canonical 一致性强校验请走 receive/batch_semantics.ensure_batch_consistent（lots 口径）
    """
    code = normalize_optional_batch_code(lot_code)
    if code is None:
        return

    _ = created_at  # lots 未必有 created_at；保留参数避免上游签名改动

    await session.execute(
        text(
            """
            INSERT INTO lots (
                warehouse_id,
                item_id,
                lot_code_source,
                lot_code,
                production_date,
                expiry_date,
                expiry_source
            )
            VALUES (
                :w, :i, 'SUPPLIER', :code, :prod, :exp, :exp_src
            )
            ON CONFLICT (warehouse_id, item_id, lot_code_source, lot_code)
            WHERE lot_code_source = 'SUPPLIER'
            DO NOTHING
            """
        ),
        {
            "i": int(item_id),
            "w": int(warehouse_id),
            "code": code,
            "prod": production_date,
            "exp": expiry_date,
            "exp_src": ("EXPLICIT" if expiry_date is not None else None),
        },
    )


# 兼容旧调用名：仍保留函数入口，但内部语义是 lot-world
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
    await ensure_lot_dict(
        session=session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        lot_code=batch_code,
        production_date=production_date,
        expiry_date=expiry_date,
        created_at=created_at,
    )
