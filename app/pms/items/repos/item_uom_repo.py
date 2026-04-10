# app/pms/items/repos/item_uom_repo.py
from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inbound_receipt import InboundReceiptLine
from app.pms.items.models.item import Item
from app.pms.items.models.item_barcode import ItemBarcode
from app.pms.items.models.item_uom import ItemUOM
from app.models.purchase_order_line import PurchaseOrderLine


def get_item_uom_by_id(db: Session, item_uom_id: int) -> ItemUOM | None:
    if not item_uom_id or item_uom_id <= 0:
        return None
    return db.get(ItemUOM, int(item_uom_id))


def list_item_uoms_by_item_id(db: Session, item_id: int) -> list[ItemUOM]:
    if not item_id or item_id <= 0:
        return []
    stmt = (
        select(ItemUOM)
        .where(ItemUOM.item_id == int(item_id))
        .order_by(ItemUOM.ratio_to_base.asc(), ItemUOM.id.asc())
    )
    return db.execute(stmt).scalars().all()


def list_item_uoms_by_item_ids(db: Session, item_ids: Sequence[int]) -> list[ItemUOM]:
    ids = sorted({int(x) for x in item_ids if int(x) > 0})
    if not ids:
        return []

    stmt = (
        select(ItemUOM)
        .where(ItemUOM.item_id.in_(ids))
        .order_by(ItemUOM.item_id.asc(), ItemUOM.ratio_to_base.asc(), ItemUOM.id.asc())
    )
    return db.execute(stmt).scalars().all()


def get_base_item_uom(db: Session, item_id: int) -> ItemUOM | None:
    if not item_id or item_id <= 0:
        return None

    stmt = (
        select(ItemUOM)
        .where(
            ItemUOM.item_id == int(item_id),
            ItemUOM.is_base.is_(True),
        )
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def get_purchase_default_item_uom(db: Session, item_id: int) -> ItemUOM | None:
    if not item_id or item_id <= 0:
        return None

    stmt = (
        select(ItemUOM)
        .where(
            ItemUOM.item_id == int(item_id),
            ItemUOM.is_purchase_default.is_(True),
        )
        .order_by(ItemUOM.is_base.desc(), ItemUOM.id.asc())
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def add_item_uom(db: Session, obj: ItemUOM) -> None:
    db.add(obj)


def create_item_uom(
    db: Session,
    *,
    item_id: int,
    uom: str,
    ratio_to_base: int,
    display_name: str | None = None,
    net_weight_kg: float | None = None,
    is_base: bool = False,
    is_purchase_default: bool = False,
    is_inbound_default: bool = False,
    is_outbound_default: bool = False,
) -> ItemUOM:
    obj = ItemUOM(
        item_id=int(item_id),
        uom=str(uom),
        ratio_to_base=int(ratio_to_base),
        display_name=display_name,
        net_weight_kg=net_weight_kg,
        is_base=bool(is_base),
        is_purchase_default=bool(is_purchase_default),
        is_inbound_default=bool(is_inbound_default),
        is_outbound_default=bool(is_outbound_default),
    )
    db.add(obj)
    return obj


def update_item_uom_fields(
    obj: ItemUOM,
    *,
    uom: str | None = None,
    ratio_to_base: int | None = None,
    display_name: str | None = None,
    net_weight_kg: float | None = None,
    is_base: bool | None = None,
    is_purchase_default: bool | None = None,
    is_inbound_default: bool | None = None,
    is_outbound_default: bool | None = None,
) -> None:
    if uom is not None:
        obj.uom = str(uom)
    if ratio_to_base is not None:
        obj.ratio_to_base = int(ratio_to_base)

    # 这些字段允许显式传 null
    obj.display_name = display_name
    obj.net_weight_kg = net_weight_kg

    if is_base is not None:
        obj.is_base = bool(is_base)
    if is_purchase_default is not None:
        obj.is_purchase_default = bool(is_purchase_default)
    if is_inbound_default is not None:
        obj.is_inbound_default = bool(is_inbound_default)
    if is_outbound_default is not None:
        obj.is_outbound_default = bool(is_outbound_default)


def delete_item_uom(db: Session, obj: ItemUOM) -> None:
    db.delete(obj)


def refresh_item_uom(db: Session, obj: ItemUOM) -> None:
    db.refresh(obj)


def has_barcode_refs_for_item_uom(
    db: Session,
    *,
    item_id: int,
    item_uom_id: int,
) -> bool:
    stmt = (
        select(ItemBarcode.id)
        .where(
            ItemBarcode.item_id == int(item_id),
            ItemBarcode.item_uom_id == int(item_uom_id),
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def has_po_line_refs_for_item_uom(db: Session, *, item_uom_id: int) -> bool:
    stmt = (
        select(PurchaseOrderLine.id)
        .where(PurchaseOrderLine.purchase_uom_id_snapshot == int(item_uom_id))
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def has_receipt_line_refs_for_item_uom(db: Session, *, item_uom_id: int) -> bool:
    stmt = (
        select(InboundReceiptLine.id)
        .where(InboundReceiptLine.uom_id == int(item_uom_id))
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def find_other_base_item_uom(
    db: Session,
    *,
    item_id: int,
    exclude_id: int,
) -> ItemUOM | None:
    stmt = (
        select(ItemUOM)
        .where(
            ItemUOM.item_id == int(item_id),
            ItemUOM.is_base.is_(True),
            ItemUOM.id != int(exclude_id),
        )
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def _barcode_rank(barcode: ItemBarcode) -> tuple[int, str, int]:
    raw_ts = barcode.updated_at or barcode.created_at
    ts = raw_ts.isoformat() if isinstance(raw_ts, datetime) else ""
    return (
        1 if bool(barcode.is_primary) else 0,
        ts,
        int(barcode.id),
    )


def _pick_barcode_by_uom(barcodes: list[ItemBarcode]) -> dict[int, ItemBarcode]:
    out: dict[int, ItemBarcode] = {}

    for barcode in barcodes:
        current = out.get(int(barcode.item_uom_id))
        if current is None or _barcode_rank(barcode) > _barcode_rank(current):
            out[int(barcode.item_uom_id)] = barcode

    return out


def list_item_uom_row_sources_by_item_ids(
    db: Session,
    *,
    item_ids: Sequence[int],
    active_only: bool,
) -> list[tuple[ItemUOM, Item, ItemBarcode | None]]:
    ids = sorted({int(x) for x in item_ids if int(x) > 0})
    if not ids:
        return []

    uom_stmt = (
        select(ItemUOM, Item)
        .join(Item, Item.id == ItemUOM.item_id)
        .where(ItemUOM.item_id.in_(ids))
        .order_by(
            Item.sku.asc(),
            Item.name.asc(),
            ItemUOM.ratio_to_base.asc(),
            ItemUOM.id.asc(),
        )
    )
    uom_pairs = db.execute(uom_stmt).all()

    barcode_stmt = select(ItemBarcode).where(ItemBarcode.item_id.in_(ids))
    if active_only:
        barcode_stmt = barcode_stmt.where(ItemBarcode.active.is_(True))

    barcode_rows = db.execute(barcode_stmt).scalars().all()
    barcode_by_uom = _pick_barcode_by_uom(list(barcode_rows))

    return [
        (uom, item, barcode_by_uom.get(int(uom.id)))
        for uom, item in uom_pairs
    ]


def flush(db: Session) -> None:
    db.flush()


def commit(db: Session) -> None:
    db.commit()


def rollback(db: Session) -> None:
    db.rollback()
