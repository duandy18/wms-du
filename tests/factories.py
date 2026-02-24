# tests/factories.py
import uuid

from app.models.item import Item
from app.models.stock import Stock
from app.models.warehouse import Warehouse


def _ensure_warehouse(db, wh_id: int) -> Warehouse:
    # 用 name 作为幂等键，避免直接指定主键 id
    name = f"WH-{wh_id}"
    wh = db.query(Warehouse).filter_by(name=name).first()
    if not wh:
        wh = Warehouse(name=name)
        db.add(wh)
        db.flush()
    return wh


def make_item(db, name: str = "Cat Food A") -> Item:
    obj = Item(sku=str(uuid.uuid4()), name=name)
    db.add(obj)
    db.flush()
    return obj


def get_stock(db, item_id: int, warehouse_id: int, batch_code=None) -> Stock:
    return (
        db.query(Stock)
        .filter(Stock.item_id == item_id, Stock.warehouse_id == warehouse_id, Stock.batch_code.is_(batch_code) if batch_code is None else Stock.batch_code == batch_code)
        .one()
    )
