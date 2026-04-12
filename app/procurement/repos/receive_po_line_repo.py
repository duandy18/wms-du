from __future__ import annotations

from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.pms.public.items.services.item_read_service import ItemReadService


async def load_item_expiry_policy(session: AsyncSession, *, item_id: int) -> str:
    svc = ItemReadService(session)
    policy = await svc.aget_policy_by_id(item_id=int(item_id))
    if policy is None:
        return "NONE"
    return str(policy.expiry_policy or "NONE").upper()


async def load_item_lot_source_policy(session: AsyncSession, *, item_id: int) -> str:
    svc = ItemReadService(session)
    policy = await svc.aget_policy_by_id(item_id=int(item_id))
    if policy is None:
        return "INTERNAL_ONLY"
    return str(policy.lot_source_policy or "INTERNAL_ONLY").upper()


async def require_item_uom_ratio_to_base(
    session: AsyncSession,
    *,
    item_id: int,
    uom_id: int,
) -> Tuple[int, Optional[str]]:
    if uom_id <= 0:
        raise HTTPException(status_code=400, detail="uom_id 必须为正整数")

    row = await session.execute(
        text(
            """
            SELECT
              ratio_to_base,
              COALESCE(NULLIF(TRIM(display_name), ''), NULLIF(TRIM(uom), '')) AS disp
            FROM item_uoms
            WHERE id = :uom_id AND item_id = :item_id
            """
        ),
        {"uom_id": int(uom_id), "item_id": int(item_id)},
    )
    r = row.mappings().first()
    if r is None:
        raise HTTPException(
            status_code=400,
            detail=f"uom_id 不存在或不属于该商品：item_id={int(item_id)} uom_id={int(uom_id)}",
        )

    try:
        ratio = int(r.get("ratio_to_base") or 0)
    except Exception:
        ratio = 0
    if ratio <= 0:
        raise HTTPException(status_code=400, detail="item_uoms.ratio_to_base 非法（必须 >= 1）")

    disp = r.get("disp")
    disp = str(disp).strip() if disp is not None and str(disp).strip() else None
    return ratio, disp


__all__ = [
    "load_item_expiry_policy",
    "load_item_lot_source_policy",
    "require_item_uom_ratio_to_base",
]
