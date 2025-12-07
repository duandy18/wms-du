# app/api/routers/stock_batch.py
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.batch import Batch
from app.models.stock import Stock
from app.schemas.stock import StockBatchQueryIn, StockBatchQueryOut, StockBatchRow

router = APIRouter(prefix="/stock/batch", tags=["stock"])


@router.post("/query", response_model=StockBatchQueryOut)
async def query_batches(
    body: StockBatchQueryIn,
    session: AsyncSession = Depends(get_session),
) -> StockBatchQueryOut:
    """
    批次视图（v2）——**以 stocks 为唯一真相**：

    - 先从 stocks 聚合 (item_id, warehouse_id, batch_code) 的当前库存 qty；
    - 再 LEFT JOIN batches 取生产/有效期等 FEFO 信息；
    - 完全忽略 batches.qty 字段，不再依赖旧时代的冗余数量。

    过滤维度：
    - item_id（必选或可选，视前端而定）
    - warehouse_id（可选）
    - expiry_date_from / expiry_date_to（基于 batches.expiry_date）
    """

    # 1) 以 stocks 为真相：按 (item_id, warehouse_id, batch_code) 聚合库存
    stocks_subq = (
        select(
            Stock.item_id.label("item_id"),
            Stock.warehouse_id.label("warehouse_id"),
            Stock.batch_code.label("batch_code"),
            func.sum(Stock.qty).label("qty"),
        )
        .group_by(Stock.item_id, Stock.warehouse_id, Stock.batch_code)
        .subquery("s")
    )

    # 2) LEFT JOIN 批次主档，补 FEFO 信息
    base = (
        select(
            Batch.id.label("batch_id"),
            stocks_subq.c.item_id,
            stocks_subq.c.warehouse_id,
            stocks_subq.c.batch_code,
            Batch.production_date,
            Batch.expiry_date,
            stocks_subq.c.qty,
        )
        .select_from(stocks_subq)
        .join(
            Batch,
            (Batch.item_id == stocks_subq.c.item_id)
            & (Batch.warehouse_id == stocks_subq.c.warehouse_id)
            & (Batch.batch_code == stocks_subq.c.batch_code),
            isouter=True,
        )
    )

    # 3) 组合过滤条件
    conds = []
    if body.item_id is not None:
        conds.append(stocks_subq.c.item_id == body.item_id)
    if body.warehouse_id is not None:
        conds.append(stocks_subq.c.warehouse_id == body.warehouse_id)
    if body.expiry_date_from is not None:
        conds.append(Batch.expiry_date >= body.expiry_date_from)
    if body.expiry_date_to is not None:
        conds.append(Batch.expiry_date <= body.expiry_date_to)
    # 只保留 qty != 0 的批次
    conds.append(stocks_subq.c.qty != 0)

    if conds:
        base = base.where(and_(*conds))

    # 4) 统计总行数（分页用）
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    # 5) FEFO 排序：有效期存在的优先；未过期优先；按到期日升序
    today = date.today()
    order_by = [
        # 没有 expiry_date 的放到后面
        case((Batch.expiry_date.is_(None), 1), else_=0),
        # 已过期的排在未过期之后（可按需要调整）
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

    return StockBatchQueryOut(
        total=total,
        page=page,
        page_size=size,
        items=items,
    )
