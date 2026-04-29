# app/pms/items/repos/item_repo.py
from __future__ import annotations

from typing import List, Optional

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

        # ✅ 主条码（primary）表达式：只命中 is_primary=true 且 active=true 的条码
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


def get_item_by_id(db: Session, id: int) -> Optional[Item]:
    if not id or id <= 0:
        return None
    return db.get(Item, id)


def get_item_by_sku(db: Session, sku: str) -> Optional[Item]:
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
