# tests/factories.py
import uuid

from app.models.item import Item
from app.models.location import Location
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


def make_location(db, wh_id: int = 1, code: str = "A-01") -> Location:
    wh = _ensure_warehouse(db, wh_id)
    loc = Location(name=code, warehouse_id=wh.id)
    db.add(loc)
    db.flush()
    return loc


def get_stock(db, item_id: int, location_id: int) -> Stock:
    return db.query(Stock).filter_by(item_id=item_id, location_id=location_id).one()
