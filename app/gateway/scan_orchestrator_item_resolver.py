# app/gateway/scan_orchestrator_item_resolver.py
from __future__ import annotations

from typing import Optional

import sqlalchemy as sa
from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item_barcode import ItemBarcode


async def resolve_item_id_from_barcode(session: AsyncSession, barcode: str) -> Optional[int]:
    code = (barcode or "").strip()
    if not code:
        return None

    stmt = (
        sa.select(ItemBarcode.item_id)
        .where(ItemBarcode.barcode == code)
        .order_by(ItemBarcode.active.desc(), ItemBarcode.id.asc())
    )

    try:
        row = await session.execute(stmt)
        item_id = row.scalar_one_or_none()
        if item_id is None:
            return None
        try:
            return int(item_id)
        except Exception:
            return None
    except Exception:
        return None


async def resolve_item_id_from_sku(session: AsyncSession, sku: str) -> Optional[int]:
    s = (sku or "").strip()
    if not s:
        return None

    try:
        row = await session.execute(
            SA("SELECT id FROM items WHERE sku = :s LIMIT 1"),
            {"s": s},
        )
        item_id = row.scalar_one_or_none()
        if item_id is None:
            return None
        return int(item_id)
    except Exception:
        return None
