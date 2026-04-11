# app/pms/items/repos/item_barcode_repo.py
from __future__ import annotations

from typing import Sequence

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.pms.items.models.item import Item
from app.pms.items.models.item_barcode import ItemBarcode
from app.pms.items.models.item_uom import ItemUOM


def get_item_barcode_by_id(db: Session, barcode_id: int) -> ItemBarcode | None:
    if not barcode_id or barcode_id <= 0:
        return None
    return db.get(ItemBarcode, int(barcode_id))


def get_item_barcode_by_code(
    db: Session,
    *,
    barcode: str,
    exclude_id: int | None = None,
) -> ItemBarcode | None:
    code = (barcode or "").strip()
    if not code:
        return None

    stmt = select(ItemBarcode).where(ItemBarcode.barcode == code)
    if exclude_id is not None:
        stmt = stmt.where(ItemBarcode.id != int(exclude_id))

    return db.execute(stmt).scalars().first()


def list_item_barcodes_by_item_id(
    db: Session,
    *,
    item_id: int,
    active_only: bool | None = None,
) -> list[ItemBarcode]:
    if not item_id or item_id <= 0:
        return []

    stmt = select(ItemBarcode).where(ItemBarcode.item_id == int(item_id))
    if active_only is True:
        stmt = stmt.where(ItemBarcode.active.is_(True))

    stmt = stmt.order_by(ItemBarcode.id.asc())
    return db.execute(stmt).scalars().all()


def list_item_barcodes_by_item_ids(
    db: Session,
    *,
    item_ids: Sequence[int],
    active_only: bool | None = None,
) -> list[ItemBarcode]:
    ids = sorted({int(x) for x in item_ids if int(x) > 0})
    if not ids:
        return []

    stmt = select(ItemBarcode).where(ItemBarcode.item_id.in_(ids))
    if active_only is True:
        stmt = stmt.where(ItemBarcode.active.is_(True))

    stmt = stmt.order_by(ItemBarcode.item_id.asc(), ItemBarcode.id.asc())
    return db.execute(stmt).scalars().all()


def load_primary_barcodes_map(
    db: Session,
    *,
    item_ids: Sequence[int],
) -> dict[int, str]:
    ids = sorted({int(x) for x in item_ids if int(x) > 0})
    if not ids:
        return {}

    rows = (
        db.execute(
            select(ItemBarcode.item_id, ItemBarcode.barcode)
            .where(ItemBarcode.item_id.in_(ids))
            .where(ItemBarcode.is_primary.is_(True))
            .where(ItemBarcode.active.is_(True))
        )
        .all()
    )

    out: dict[int, str] = {}
    for item_id, barcode in rows:
        if item_id is None or barcode is None:
            continue
        out[int(item_id)] = str(barcode)
    return out


def has_barcode_bound_to_item_uom(
    db: Session,
    *,
    item_id: int,
    item_uom_id: int,
    exclude_barcode_id: int | None = None,
) -> bool:
    stmt = select(ItemBarcode.id).where(
        ItemBarcode.item_id == int(item_id),
        ItemBarcode.item_uom_id == int(item_uom_id),
    )
    if exclude_barcode_id is not None:
        stmt = stmt.where(ItemBarcode.id != int(exclude_barcode_id))

    return db.execute(stmt.limit(1)).scalar_one_or_none() is not None


def add_item_barcode(db: Session, obj: ItemBarcode) -> None:
    db.add(obj)


def create_item_barcode(
    db: Session,
    *,
    item_id: int,
    item_uom_id: int,
    barcode: str,
    symbology: str,
    active: bool,
    is_primary: bool,
) -> ItemBarcode:
    obj = ItemBarcode(
        item_id=int(item_id),
        item_uom_id=int(item_uom_id),
        barcode=str(barcode),
        symbology=str(symbology),
        active=bool(active),
        is_primary=bool(is_primary),
    )
    db.add(obj)
    return obj


def update_item_barcode_fields(
    obj: ItemBarcode,
    *,
    item_uom_id: int | None = None,
    barcode: str | None = None,
    symbology: str | None = None,
    active: bool | None = None,
    is_primary: bool | None = None,
) -> None:
    if item_uom_id is not None:
        obj.item_uom_id = int(item_uom_id)
    if barcode is not None:
        obj.barcode = str(barcode)
    if symbology is not None:
        obj.symbology = str(symbology)
    if active is not None:
        obj.active = bool(active)
    if is_primary is not None:
        obj.is_primary = bool(is_primary)


def clear_primary_flags_for_item(db: Session, *, item_id: int) -> None:
    db.execute(
        update(ItemBarcode)
        .where(ItemBarcode.item_id == int(item_id))
        .values(is_primary=False)
    )


def delete_item_barcode(db: Session, obj: ItemBarcode) -> None:
    db.delete(obj)


def refresh_item_barcode(db: Session, obj: ItemBarcode) -> None:
    db.refresh(obj)


def get_item_uom_by_id(db: Session, item_uom_id: int) -> ItemUOM | None:
    if not item_uom_id or item_uom_id <= 0:
        return None
    return db.get(ItemUOM, int(item_uom_id))


def list_barcode_row_sources_for_item(
    db: Session,
    *,
    item_id: int,
    active_only: bool,
) -> list[tuple[ItemBarcode, ItemUOM, Item]]:
    if not item_id or item_id <= 0:
        return []

    stmt = (
        select(ItemBarcode, ItemUOM, Item)
        .join(
            ItemUOM,
            (ItemUOM.id == ItemBarcode.item_uom_id)
            & (ItemUOM.item_id == ItemBarcode.item_id),
        )
        .join(Item, Item.id == ItemBarcode.item_id)
        .where(ItemBarcode.item_id == int(item_id))
    )

    if active_only:
        stmt = stmt.where(ItemBarcode.active.is_(True))

    stmt = stmt.order_by(
        ItemUOM.ratio_to_base.asc(),
        ItemUOM.id.asc(),
        ItemBarcode.id.asc(),
    )
    return db.execute(stmt).all()


def flush(db: Session) -> None:
    db.flush()


def commit(db: Session) -> None:
    db.commit()


def rollback(db: Session) -> None:
    db.rollback()
