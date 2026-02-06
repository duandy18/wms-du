# app/services/item_repo.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models.item import Item


def get_items(
    db: Session,
    *,
    supplier_id: Optional[int] = None,
    enabled: Optional[bool] = None,
    q: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Item]:
    stmt = select(Item)

    if supplier_id is not None:
        stmt = stmt.where(Item.supplier_id == supplier_id)

    if enabled is not None:
        stmt = stmt.where(Item.enabled == enabled)

    q_raw = (q or "").strip()
    if q_raw:
        q_like = f"%{q_raw.lower()}%"

        conds = [
            func.lower(Item.sku).like(q_like),
            func.lower(Item.name).like(q_like),
            cast(Item.id, String).like(q_like),
        ]

        # barcode：只从真实表列读取，避免拿到 Python @property
        barcode_col = None
        try:
            barcode_col = Item.__table__.c.get("barcode")  # type: ignore[attr-defined]
        except Exception:
            barcode_col = None

        if barcode_col is not None:
            conds.append(func.lower(barcode_col).like(q_like))

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


def get_item_by_id(db: Session, id: int) -> Optional[Item]:
    if not id or id <= 0:
        return None
    return db.get(Item, id)


def get_item_by_sku(db: Session, sku: str) -> Optional[Item]:
    s = (sku or "").strip()
    if not s:
        return None
    return db.execute(select(Item).where(Item.sku == s)).scalar_one_or_none()
