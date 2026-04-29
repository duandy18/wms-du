# app/pms/items/repos/item_write_repo.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.pms.items.models.item import Item
from app.pms.items.models.item_barcode import ItemBarcode
from app.pms.items.models.item_sku_code import ItemSkuCode


def _active_sku_code_match_exists(*, q_like: str):
    return (
        select(ItemSkuCode.id)
        .where(ItemSkuCode.item_id == Item.id)
        .where(ItemSkuCode.is_active.is_(True))
        .where(func.lower(ItemSkuCode.code).like(q_like))
        .limit(1)
        .exists()
    )


def list_items(
    db: Session,
    *,
    supplier_id: Optional[int] = None,
    enabled: Optional[bool] = None,
    q: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[Item]:
    stmt = select(Item)

    if supplier_id is not None:
        stmt = stmt.where(Item.supplier_id == supplier_id)

    if enabled is not None:
        stmt = stmt.where(Item.enabled == enabled)

    q_raw = (q or "").strip()
    if q_raw:
        q_like = f"%{q_raw.lower()}%"

        primary_barcode_expr = (
            select(ItemBarcode.barcode)
            .where(ItemBarcode.item_id == Item.id)
            .where(ItemBarcode.is_primary.is_(True))
            .where(ItemBarcode.active.is_(True))
            .limit(1)
            .scalar_subquery()
        )

        conds = [
            func.lower(Item.sku).like(q_like),
            _active_sku_code_match_exists(q_like=q_like),
            func.lower(Item.name).like(q_like),
            cast(Item.id, String).like(q_like),
            func.lower(func.coalesce(primary_barcode_expr, "")).like(q_like),
        ]

        if q_raw.isdigit():
            try:
                conds.append(Item.id == int(q_raw))
            except Exception:
                pass

        stmt = stmt.where(or_(*conds))

    lim: Optional[int] = None
    if limit is not None:
        try:
            x = int(limit)
            if x > 0:
                lim = x
        except Exception:
            lim = None
    elif q_raw:
        lim = 50

    stmt = stmt.order_by(Item.id.asc())
    if lim is not None:
        stmt = stmt.limit(lim)

    return db.execute(stmt).scalars().all()


def get_item_by_id(db: Session, item_id: int) -> Item | None:
    if not item_id or item_id <= 0:
        return None
    return db.get(Item, int(item_id))


def get_item_by_id_for_update(db: Session, item_id: int) -> Item | None:
    if not item_id or item_id <= 0:
        return None
    return db.get(Item, int(item_id))


def get_item_by_sku(db: Session, sku: str) -> Item | None:
    s = (sku or "").strip().upper()
    if not s:
        return None

    row = (
        db.execute(
            select(ItemSkuCode)
            .where(func.lower(ItemSkuCode.code) == s.lower())
            .where(ItemSkuCode.is_active.is_(True))
            .order_by(ItemSkuCode.is_primary.desc(), ItemSkuCode.id.asc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is not None:
        return db.get(Item, int(row.item_id))

    return None


def add_item(db: Session, item: Item) -> None:
    db.add(item)


def flush(db: Session) -> None:
    db.flush()


def refresh_item(db: Session, item: Item) -> None:
    db.refresh(item)


def commit(db: Session) -> None:
    db.commit()


def rollback(db: Session) -> None:
    db.rollback()
