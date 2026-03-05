# app/services/purchase_order_enrichment.py
from __future__ import annotations

from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.item_barcode import ItemBarcode


async def load_items_map(session: AsyncSession, item_ids: List[int]) -> Dict[int, Item]:
    if not item_ids:
        return {}
    rows = (await session.execute(select(Item).where(Item.id.in_(item_ids)))).scalars().all()
    return {int(it.id): it for it in rows}


async def load_primary_barcodes(session: AsyncSession, item_ids: List[int]) -> Dict[int, str]:
    """
    主条码规则（与 snapshot_inventory.py 保持一致）：
    - 仅 active=true
    - is_primary 优先，否则最小 id（稳定且可解释）
    """
    if not item_ids:
        return {}

    rows = (
        (
            await session.execute(
                select(ItemBarcode)
                .where(ItemBarcode.item_id.in_(item_ids), ItemBarcode.active.is_(True))
                .order_by(
                    ItemBarcode.item_id.asc(),
                    ItemBarcode.is_primary.desc(),
                    ItemBarcode.id.asc(),
                )
            )
        )
        .scalars()
        .all()
    )

    m: Dict[int, str] = {}
    for bc in rows:
        iid = int(bc.item_id)
        if iid in m:
            continue
        m[iid] = bc.barcode
    return m
