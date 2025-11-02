# app/api/endpoints/stock_batch.py
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.batch import Batch
from app.schemas.stock import StockBatchQueryIn, StockBatchQueryOut, StockBatchRow

router = APIRouter(prefix="/stock/batch", tags=["stock"])


@router.post("/query", response_model=StockBatchQueryOut)
async def query_batches(
    body: StockBatchQueryIn,
    session: AsyncSession = Depends(get_session),
) -> StockBatchQueryOut:
    # 直接从 batches 表查询（qty 为真相源）
    base = select(
        Batch.id.label("batch_id"),
        Batch.item_id,
        Batch.warehouse_id,
        Batch.batch_code,
        Batch.production_date,
        Batch.expiry_date,
        Batch.qty.label("qty"),
    )

    conds = []
    if body.item_id is not None:
        conds.append(Batch.item_id == body.item_id)
    if body.warehouse_id is not None:
        conds.append(Batch.warehouse_id == body.warehouse_id)
    if body.expiry_date_from is not None:
        conds.append(Batch.expiry_date >= body.expiry_date_from)
    if body.expiry_date_to is not None:
        conds.append(Batch.expiry_date <= body.expiry_date_to)
    # 只看有量的批次（>=1）；若你希望展示空批次，把这一行去掉即可
    conds.append(Batch.qty != 0)
    if conds:
        base = base.where(and_(*conds))

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    today = date.today()
    order_by = [
        # FEFO 友好：已过期优先 → 最近到期 → 无到期 → id
        case((Batch.expiry_date.is_(None), 1), else_=0),
        case((Batch.expiry_date < today, 0), else_=1),
        Batch.expiry_date.asc().nulls_last(),
        Batch.id.asc(),
    ]

    page = max(1, body.page)
    size = max(1, min(500, body.page_size))
    rows = (
        await session.execute(base.order_by(*order_by).offset((page - 1) * size).limit(size))
    ).all()

    items: list[StockBatchRow] = []
    for r in rows:
        expiry = r.expiry_date
        dte = (expiry - today).days if expiry else None
        items.append(
            StockBatchRow(
                batch_id=r.batch_id,
                item_id=r.item_id,
                warehouse_id=r.warehouse_id,
                batch_code=r.batch_code,
                qty=int(r.qty or 0),
                production_date=r.production_date,
                expiry_date=expiry,
                days_to_expiry=dte,
            )
        )

    return StockBatchQueryOut(total=total, page=page, page_size=size, items=items)
