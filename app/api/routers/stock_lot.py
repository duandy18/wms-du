# app/api/routers/stock_lot.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.lot import Lot
from app.models.stock_lot import StockLot
from app.schemas.stock_lot import StockLotQueryIn, StockLotQueryOut, StockLotRow

router = APIRouter(prefix="/stock/lot", tags=["stock"])


@router.post("/query", response_model=StockLotQueryOut)
async def query_lots(
    body: StockLotQueryIn,
    session: AsyncSession = Depends(get_session),
) -> StockLotQueryOut:
    """
    lot 视图（Phase M-2 终态）——以 stocks_lot 为读取来源（ORM 版）：

    - 从 stocks_lot 读取 (item_id, warehouse_id, lot_id) 的余额 qty
    - LEFT JOIN lots 补充 lot_code / 生产日期 / 失效日期等展示字段
    - lot_id 在结构封板后不再允许为空
    """

    stmt = (
        select(
            StockLot.item_id,
            StockLot.warehouse_id,
            StockLot.lot_id,
            Lot.lot_code_source,
            Lot.lot_code,
            Lot.production_date,
            Lot.expiry_date,
            StockLot.qty,
        )
        .select_from(StockLot)
        .join(Lot, Lot.id == StockLot.lot_id, isouter=True)
    )

    if body.item_id is not None:
        stmt = stmt.where(StockLot.item_id == int(body.item_id))

    if body.warehouse_id is not None:
        stmt = stmt.where(StockLot.warehouse_id == int(body.warehouse_id))

    if body.lot_id is not None:
        stmt = stmt.where(StockLot.lot_id == int(body.lot_id))

    if body.qty_nonzero_only:
        stmt = stmt.where(StockLot.qty != 0)

    stmt = stmt.order_by(StockLot.warehouse_id, StockLot.item_id, StockLot.lot_id)

    rows = (await session.execute(stmt)).all()

    out_rows: list[StockLotRow] = [
        StockLotRow(
            item_id=int(r[0]),
            warehouse_id=int(r[1]),
            lot_id=int(r[2]),
            lot_code_source=(str(r[3]) if r[3] is not None else None),
            lot_code=(str(r[4]) if r[4] is not None else None),
            production_date=r[5],
            expiry_date=r[6],
            qty=int(r[7] or 0),
        )
        for r in rows
    ]

    return StockLotQueryOut(rows=out_rows)
