# app/services/domain/lot_service.py
from __future__ import annotations

from typing import Literal, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.lot import Lot
from app.services.stock.lots import ensure_internal_lot_singleton, ensure_lot_full


def _snapshot_equal(existing: Lot, incoming: dict) -> bool:
    return (
        existing.item_shelf_life_value_snapshot == incoming["item_shelf_life_value_snapshot"]
        and existing.item_shelf_life_unit_snapshot == incoming["item_shelf_life_unit_snapshot"]
        and existing.item_lot_source_policy_snapshot == incoming["item_lot_source_policy_snapshot"]
        and existing.item_expiry_policy_snapshot == incoming["item_expiry_policy_snapshot"]
        and existing.item_derivation_allowed_snapshot == incoming["item_derivation_allowed_snapshot"]
        and existing.item_uom_governance_enabled_snapshot == incoming["item_uom_governance_enabled_snapshot"]
    )


async def resolve_or_create_lot(
    *,
    db: AsyncSession,
    warehouse_id: int,
    item: Item,
    lot_code_source: Literal["SUPPLIER", "INTERNAL"],
    lot_code: Optional[str],
    source_receipt_id: Optional[int],
    source_line_no: Optional[int],
) -> int:
    """
    领域层兼容入口（收口）：
    - SUPPLIER: ensure_lot_full (lot_code_key)
    - INTERNAL: ensure_internal_lot_singleton (wh+item singleton; provenance optional but paired)
    """
    expiry_policy = getattr(item, "expiry_policy", None)

    snapshot = {
        "item_shelf_life_value_snapshot": getattr(item, "shelf_life_value", None),
        "item_shelf_life_unit_snapshot": getattr(item, "shelf_life_unit", None),
        "item_lot_source_policy_snapshot": getattr(item, "lot_source_policy"),
        "item_expiry_policy_snapshot": expiry_policy,
        "item_derivation_allowed_snapshot": bool(getattr(item, "derivation_allowed")),
        "item_uom_governance_enabled_snapshot": bool(getattr(item, "uom_governance_enabled")),
    }

    if snapshot["item_lot_source_policy_snapshot"] is None:
        raise HTTPException(status_code=500, detail="item_policy_missing:lot_source_policy")
    if snapshot["item_expiry_policy_snapshot"] is None:
        raise HTTPException(status_code=500, detail="item_policy_missing:expiry_policy")

    if lot_code_source == "SUPPLIER":
        if not lot_code or not str(lot_code).strip():
            raise HTTPException(status_code=422, detail="supplier_lot_code_required")

        lot_id = await ensure_lot_full(
            db,
            item_id=int(item.id),
            warehouse_id=int(warehouse_id),
            lot_code=str(lot_code),
            production_date=None,
            expiry_date=None,
        )

        existing = (await db.execute(select(Lot).where(Lot.id == int(lot_id)))).scalars().first()
        if existing is None:
            raise HTTPException(status_code=500, detail="lot_create_or_resolve_failed")

        if not _snapshot_equal(existing, snapshot):
            raise HTTPException(status_code=409, detail="lot_snapshot_conflict")
        return int(existing.id)

    # INTERNAL singleton
    try:
        return int(
            await ensure_internal_lot_singleton(
                db,
                item_id=int(item.id),
                warehouse_id=int(warehouse_id),
                source_receipt_id=int(source_receipt_id) if source_receipt_id is not None else None,
                source_line_no=int(source_line_no) if source_line_no is not None else None,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
