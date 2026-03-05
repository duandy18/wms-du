# app/api/routers/stock_batch.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.lot import Lot
from app.models.stock_lot import StockLot
from app.schemas.stock import StockBatchQueryIn, StockBatchQueryOut

router = APIRouter(prefix="/stock/batch", tags=["stock"])


def _get_page(body: StockBatchQueryIn) -> int:
    v = getattr(body, "page", None)
    try:
        iv = int(v) if v is not None else 1
    except Exception:
        iv = 1
    return iv if iv >= 1 else 1


def _get_page_size(body: StockBatchQueryIn) -> int:
    v = getattr(body, "page_size", None)
    try:
        iv = int(v) if v is not None else 50
    except Exception:
        iv = 50
    if iv <= 0:
        return 50
    return min(iv, 500)


@router.post("/query", response_model=StockBatchQueryOut)
async def query_batches(
    body: StockBatchQueryIn,
    session: AsyncSession = Depends(get_session),
) -> StockBatchQueryOut:
    """
    批次视图（Phase 4B-3 已切读到 stocks_lot）：

    - 以 stocks_lot 为余额来源（qty）
    - LEFT JOIN lots 补充批次展示信息
    - 不再从 stocks 读取 qty
    - batch_code 语义来自 lots.lot_code

    输出保持 StockBatchQueryOut 契约（total/page/page_size/items），并在每行返回 qty。
    """

    page = _get_page(body)
    page_size = _get_page_size(body)
    offset = (page - 1) * page_size

    # 1) 以 stocks_lot 为余额事实（按 item/wh/lot 聚合）
    stocks_subq = (
        select(
            StockLot.item_id.label("item_id"),
            StockLot.warehouse_id.label("warehouse_id"),
            StockLot.lot_id.label("lot_id"),
            func.sum(StockLot.qty).label("qty"),
        )
        .group_by(StockLot.item_id, StockLot.warehouse_id, StockLot.lot_id)
        .subquery("s")
    )

    # 2) LEFT JOIN lots 补充展示字段（兼容旧字段名：batch_*）
    base = (
        select(
            Lot.id.label("batch_id"),
            stocks_subq.c.item_id,
            stocks_subq.c.warehouse_id,
            Lot.lot_code.label("batch_code"),
            Lot.production_date,
            Lot.expiry_date,
            stocks_subq.c.qty,
        )
        .select_from(stocks_subq)
        .join(Lot, Lot.id == stocks_subq.c.lot_id, isouter=True)
    )

    # 3) 组合过滤条件
    conds = []

    if body.item_id is not None:
        conds.append(stocks_subq.c.item_id == body.item_id)

    if body.warehouse_id is not None:
        conds.append(stocks_subq.c.warehouse_id == body.warehouse_id)

    if body.expiry_date_from is not None:
        conds.append(Lot.expiry_date >= body.expiry_date_from)

    if body.expiry_date_to is not None:
        conds.append(Lot.expiry_date <= body.expiry_date_to)

    # 只保留 qty != 0 的批次
    conds.append(stocks_subq.c.qty != 0)

    if conds:
        base = base.where(and_(*conds))

    # 4) total（用于分页）
    total_stmt = select(func.count()).select_from(base.subquery("q"))
    total = int((await session.execute(total_stmt)).scalar_one() or 0)

    # 5) 分页 + 排序
    base = (
        base.order_by(
            stocks_subq.c.warehouse_id,
            stocks_subq.c.item_id,
            Lot.expiry_date.nullslast(),
            Lot.id.nullslast(),
        )
        .offset(offset)
        .limit(page_size)
    )

    rows = (await session.execute(base)).mappings().all()

    return StockBatchQueryOut(
        total=total,
        page=page,
        page_size=page_size,
        items=[
            {
                "batch_id": r["batch_id"],
                "item_id": int(r["item_id"]),
                "warehouse_id": int(r["warehouse_id"]),
                "batch_code": r["batch_code"],
                "production_date": r["production_date"],
                "expiry_date": r["expiry_date"],
                "qty": int(r["qty"] or 0),
            }
            for r in rows
        ],
    )
