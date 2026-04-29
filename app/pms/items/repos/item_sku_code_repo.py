# app/pms/items/repos/item_sku_code_repo.py
from __future__ import annotations

from typing import Iterable

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.pms.items.models.item import Item
from app.pms.items.models.item_sku_code import ItemSkuCode


def list_sku_codes_by_item_id(db: Session, *, item_id: int) -> list[ItemSkuCode]:
    return (
        db.execute(
            select(ItemSkuCode)
            .where(ItemSkuCode.item_id == int(item_id))
            .order_by(
                ItemSkuCode.is_primary.desc(),
                ItemSkuCode.is_active.desc(),
                ItemSkuCode.id.asc(),
            )
        )
        .scalars()
        .all()
    )


def get_sku_code_by_id(db: Session, *, code_id: int) -> ItemSkuCode | None:
    return db.get(ItemSkuCode, int(code_id))


def get_sku_code_by_code(db: Session, *, code: str) -> ItemSkuCode | None:
    s = str(code or "").strip().upper()
    if not s:
        return None
    return (
        db.execute(select(ItemSkuCode).where(func.lower(ItemSkuCode.code) == s.lower()))
        .scalars()
        .first()
    )


def get_active_sku_code_by_code(db: Session, *, code: str) -> ItemSkuCode | None:
    s = str(code or "").strip().upper()
    if not s:
        return None
    return (
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


def get_primary_sku_code_by_item_id(db: Session, *, item_id: int) -> ItemSkuCode | None:
    return (
        db.execute(
            select(ItemSkuCode)
            .where(ItemSkuCode.item_id == int(item_id))
            .where(ItemSkuCode.is_primary.is_(True))
            .limit(1)
        )
        .scalars()
        .first()
    )


def item_sku_code_exists_expr(*, item_id_col) -> object:
    return (
        select(ItemSkuCode.id)
        .where(ItemSkuCode.item_id == item_id_col)
        .where(ItemSkuCode.is_active.is_(True))
        .exists()
    )


def active_code_match_exists_expr(*, item_id_col, q_like: str) -> object:
    return (
        select(ItemSkuCode.id)
        .where(ItemSkuCode.item_id == item_id_col)
        .where(ItemSkuCode.is_active.is_(True))
        .where(func.lower(ItemSkuCode.code).like(q_like))
        .exists()
    )


def find_items_by_active_sku_code(db: Session, *, code: str) -> Item | None:
    row = get_active_sku_code_by_code(db, code=code)
    if row is None:
        return None
    return db.get(Item, int(row.item_id))


def add_sku_code(db: Session, obj: ItemSkuCode) -> None:
    db.add(obj)


def add_all_sku_codes(db: Session, rows: Iterable[ItemSkuCode]) -> None:
    db.add_all(list(rows))


def has_active_code_for_item(db: Session, *, item_id: int, code: str) -> bool:
    s = str(code or "").strip().upper()
    if not s:
        return False
    return bool(
        db.execute(
            select(
                exists().where(
                    ItemSkuCode.item_id == int(item_id),
                    func.lower(ItemSkuCode.code) == s.lower(),
                    ItemSkuCode.is_active.is_(True),
                )
            )
        ).scalar()
    )


def search_items_by_code_or_projection(
    db: Session,
    *,
    q_like: str,
    base_stmt,
    item_id_col,
):
    code_exists = active_code_match_exists_expr(item_id_col=item_id_col, q_like=q_like)
    return base_stmt.where(or_(code_exists, func.lower(Item.sku).like(q_like)))
