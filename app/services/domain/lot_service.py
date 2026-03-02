# app/services/domain/lot_service.py
from __future__ import annotations

from typing import Literal, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.lot import Lot


def _snapshot_equal(existing: Lot, incoming: dict) -> bool:
    """
    Phase M-5：lots 退出单位快照承载（unit_governance 二阶段）
    - 复用/冲突判定只比较“策略/货架期”快照
    - lots 的单位快照列已物理移除（migration 已 drop）
    """
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
        if not lot_code:
            raise HTTPException(status_code=422, detail="supplier_lot_code_required")

        stmt = select(Lot).where(
            Lot.warehouse_id == warehouse_id,
            Lot.item_id == item.id,
            Lot.lot_code_source == "SUPPLIER",
            Lot.lot_code == lot_code,
        )
    else:
        if not source_receipt_id or source_line_no is None:
            raise HTTPException(status_code=422, detail="internal_lot_source_required")

        stmt = select(Lot).where(
            Lot.warehouse_id == warehouse_id,
            Lot.item_id == item.id,
            Lot.lot_code_source == "INTERNAL",
            Lot.source_receipt_id == source_receipt_id,
            Lot.source_line_no == source_line_no,
        )

    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        if lot_code_source == "INTERNAL":
            return int(existing.id)
        if not _snapshot_equal(existing, snapshot):
            raise HTTPException(status_code=409, detail="lot_snapshot_conflict")
        return int(existing.id)

    new_lot = Lot(
        warehouse_id=warehouse_id,
        item_id=item.id,
        lot_code_source=lot_code_source,
        lot_code=lot_code,
        source_receipt_id=source_receipt_id,
        source_line_no=source_line_no,
        item_shelf_life_value_snapshot=snapshot["item_shelf_life_value_snapshot"],
        item_shelf_life_unit_snapshot=snapshot["item_shelf_life_unit_snapshot"],
        item_lot_source_policy_snapshot=snapshot["item_lot_source_policy_snapshot"],
        item_expiry_policy_snapshot=snapshot["item_expiry_policy_snapshot"],
        item_derivation_allowed_snapshot=snapshot["item_derivation_allowed_snapshot"],
        item_uom_governance_enabled_snapshot=snapshot["item_uom_governance_enabled_snapshot"],
    )

    db.add(new_lot)

    try:
        await db.flush()
        return int(new_lot.id)
    except IntegrityError:
        await db.rollback()
        result = await db.execute(stmt)
        existing2 = result.scalar_one()
        if lot_code_source == "SUPPLIER":
            if not _snapshot_equal(existing2, snapshot):
                raise HTTPException(status_code=409, detail="lot_snapshot_conflict")
        return int(existing2.id)
