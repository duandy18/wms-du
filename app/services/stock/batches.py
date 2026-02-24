# app/services/stock/batches.py
from __future__ import annotations

from sqlalchemy import and_, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.batch import Batch

from .accessors import batch_code_attr
from .retry import exec_retry


async def ensure_batch_full(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str,
    production_date,
    expiry_date,
) -> int:
    """
    确保 batches 行存在并补齐必要字段；返回 batch_id（幂等）。

    ✅ 当前 DB batches 唯一维度：(item_id, warehouse_id, batch_code)
    """
    code_attr = batch_code_attr()

    conds = [
        Batch.item_id == item_id,
        Batch.warehouse_id == warehouse_id,
        code_attr == batch_code,
    ]
    existed = (await session.execute(select(Batch.id).where(and_(*conds)))).scalar_one_or_none()
    if existed:
        return int(existed)

    vals = {
        "item_id": item_id,
        "warehouse_id": warehouse_id,
        code_attr.key: batch_code,
        "production_date": production_date,
        "expiry_date": expiry_date,
    }
    if hasattr(Batch, "qty"):
        vals["qty"] = 0

    try:
        rid = (await exec_retry(session, insert(Batch).values(vals).returning(Batch.id))).scalar_one()
        return int(rid)
    except IntegrityError:
        await session.rollback()
        rid2 = (await session.execute(select(Batch.id).where(and_(*conds)))).scalar_one()
        return int(rid2)
