# app/api/routers/stock.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.item import Item
from app.models.location import Location
from app.models.stock import Stock

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/query")
def stock_query(
    item_id: int | None = None,
    warehouse_id: int | None = None,
    location_id: int | None = None,
    q: str | None = Query(None, description="模糊搜索 items.name / items.sku"),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Stock.item_id, Stock.location_id, Stock.qty)
        .select_from(Stock)
        .join(Item, Item.id == Stock.item_id)
    )
    if warehouse_id is not None:
        stmt = stmt.join(Location, Location.id == Stock.location_id).where(
            Location.warehouse_id == warehouse_id
        )
    if item_id is not None:
        stmt = stmt.where(Stock.item_id == item_id)
    if location_id is not None:
        stmt = stmt.where(Stock.location_id == location_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Item.name.ilike(like)) | (Item.sku.ilike(like)))
    stmt = stmt.order_by(Stock.item_id.asc(), Stock.location_id.asc()).limit(200)

    rows = db.execute(stmt).all()
    out_rows: list[dict] = []
    on_hand = 0
    for item_id_val, loc_id_val, qty in rows:
        qty_i = int(qty or 0)
        on_hand += qty_i
        out_rows.append(
            {
                "item_id": int(item_id_val),
                "location_id": int(loc_id_val),
                "qty": qty_i,
                "available": qty_i,
            }
        )
    return {"rows": out_rows, "summary": [{"item_id": item_id or 0, "on_hand": on_hand}]}
