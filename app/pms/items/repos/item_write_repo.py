# app/pms/items/repos/item_write_repo.py
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.item import Item


def get_item_by_id_for_update(db: Session, item_id: int) -> Item | None:
    if not item_id or item_id <= 0:
        return None
    return db.get(Item, int(item_id))


def add_item(db: Session, item: Item) -> None:
    db.add(item)


def flush(db: Session) -> None:
    db.flush()


def refresh_item(db: Session, item: Item) -> None:
    db.refresh(item)
