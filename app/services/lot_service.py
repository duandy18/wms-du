# app/services/lot_service.py
from __future__ import annotations

from typing import Optional

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
    - 已移除 lots 的单位快照列（migration 已 drop），此处不再涉及单位字段
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
    db: AsyncSession,
    *,
    warehouse_id: int,
    item: Item,
    lot_code_source: str,
    lot_code: Optional[str],
    source_receipt_id: Optional[int],
    source_line_no: Optional[int],
) -> int:
    """
    兼容层 lot 创建/解析（Phase M-5）：
    - lots 承载身份 + 主数据策略快照（lot_source/expiry/derivation/shelf_life/uom_governance）
    - 时间事实（production/expiry）不写 lots，统一在 stock_ledger（reason_canon='RECEIPT'）体现
    - Phase M-5：lots 的单位快照列已物理移除
    """
    lot_code_source_u = str(lot_code_source or "").upper().strip()
    if lot_code_source_u not in ("SUPPLIER", "INTERNAL"):
        raise HTTPException(status_code=422, detail="invalid_lot_code_source")

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

    if lot_code_source_u == "SUPPLIER":
        if not lot_code or not str(lot_code).strip():
            raise HTTPException(status_code=422, detail="supplier_lot_code_required")

        stmt = select(Lot).where(
            Lot.warehouse_id == int(warehouse_id),
            Lot.item_id == int(item.id),
            Lot.lot_code_source == "SUPPLIER",
            Lot.lot_code == str(lot_code).strip(),
        )
    else:
        if source_receipt_id is None or source_line_no is None:
            raise HTTPException(status_code=422, detail="internal_lot_source_required")

        stmt = select(Lot).where(
            Lot.warehouse_id == int(warehouse_id),
            Lot.item_id == int(item.id),
            Lot.lot_code_source == "INTERNAL",
            Lot.source_receipt_id == int(source_receipt_id),
            Lot.source_line_no == int(source_line_no),
        )

    existing = (await db.execute(stmt)).scalars().first()
    if existing:
        if lot_code_source_u == "INTERNAL":
            return int(existing.id)
        if not _snapshot_equal(existing, snapshot):
            raise HTTPException(status_code=409, detail="lot_snapshot_conflict")
        return int(existing.id)

    new_lot = Lot(
        warehouse_id=int(warehouse_id),
        item_id=int(item.id),
        lot_code_source=lot_code_source_u,
        lot_code=(str(lot_code).strip() if lot_code is not None else None),
        source_receipt_id=int(source_receipt_id) if source_receipt_id is not None else None,
        source_line_no=int(source_line_no) if source_line_no is not None else None,
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
        existing2 = (await db.execute(stmt)).scalars().first()
        if existing2 is None:
            raise HTTPException(status_code=500, detail="lot_create_race_failed")
        if lot_code_source_u == "SUPPLIER":
            if not _snapshot_equal(existing2, snapshot):
                raise HTTPException(status_code=409, detail="lot_snapshot_conflict")
        return int(existing2.id)
