# app/pms/items/repos/item_aggregate_read_repo.py
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.pms.items.models.item import Item
from app.pms.items.models.item_barcode import ItemBarcode
from app.pms.items.models.item_uom import ItemUOM
from app.pms.items.repos.item_barcode_repo import list_item_barcodes_by_item_id
from app.pms.items.repos.item_uom_repo import list_item_uoms_by_item_id


@dataclass(slots=True)
class ItemAggregateRecord:
    item: Item
    uoms: list[ItemUOM]
    barcodes: list[ItemBarcode]


def get_item_aggregate_record(
    db: Session,
    *,
    item_id: int,
    active_only: bool | None = None,
) -> ItemAggregateRecord | None:
    if not item_id or int(item_id) <= 0:
        return None

    item = db.get(Item, int(item_id))
    if item is None:
        return None

    uoms = list_item_uoms_by_item_id(db, int(item_id))
    barcodes = list_item_barcodes_by_item_id(
        db,
        item_id=int(item_id),
        active_only=active_only,
    )
    return ItemAggregateRecord(
        item=item,
        uoms=uoms,
        barcodes=barcodes,
    )
