# app/services/domain/lot_service.py

from __future__ import annotations

from datetime import date
from typing import Optional, Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.lot import Lot


def _snapshot_equal(existing: Lot, incoming: dict) -> bool:
    return (
        existing.production_date == incoming["production_date"]
        and existing.expiry_date == incoming["expiry_date"]
        and existing.expiry_source == incoming["expiry_source"]
        and existing.shelf_life_days_applied == incoming["shelf_life_days_applied"]
        and existing.item_has_shelf_life_snapshot == incoming["item_has_shelf_life_snapshot"]
        and existing.item_shelf_life_value_snapshot == incoming["item_shelf_life_value_snapshot"]
        and existing.item_shelf_life_unit_snapshot == incoming["item_shelf_life_unit_snapshot"]
        and existing.item_uom_snapshot == incoming["item_uom_snapshot"]
        and existing.item_case_ratio_snapshot == incoming["item_case_ratio_snapshot"]
        and existing.item_case_uom_snapshot == incoming["item_case_uom_snapshot"]
        # Phase M policy snapshots (NOT NULL in DB)
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
    production_date: Optional[date],
    expiry_date: Optional[date],
    expiry_source: Optional[str],
    shelf_life_days_applied: Optional[int],
) -> int:
    # ---------------------------
    # 构造 snapshot
    # ---------------------------
    # NOTE:
    # - Phase M：policy 字段已在 DB NOT NULL，必须写入 lots snapshot，否则插入会失败。
    # - has_shelf_life 已被约束锁死为 expiry_policy 的镜像字段；业务规则以后应以 expiry_policy 为准。
    snapshot = {
        "production_date": production_date,
        "expiry_date": expiry_date,
        "expiry_source": expiry_source,
        "shelf_life_days_applied": shelf_life_days_applied,
        "item_has_shelf_life_snapshot": item.has_shelf_life,
        "item_shelf_life_value_snapshot": item.shelf_life_value,
        "item_shelf_life_unit_snapshot": item.shelf_life_unit,
        "item_uom_snapshot": item.uom,  # ✅ 修正：使用真实字段 uom
        "item_case_ratio_snapshot": item.case_ratio,
        "item_case_uom_snapshot": item.case_uom,
        # Phase M: policy snapshots
        "item_lot_source_policy_snapshot": getattr(item, "lot_source_policy"),
        "item_expiry_policy_snapshot": getattr(item, "expiry_policy"),
        "item_derivation_allowed_snapshot": bool(getattr(item, "derivation_allowed")),
        "item_uom_governance_enabled_snapshot": bool(getattr(item, "uom_governance_enabled")),
    }

    # 快速防御：若 item 模型还没更新导致 policy 取不到，直接暴露（比 silent drift 强）
    if snapshot["item_lot_source_policy_snapshot"] is None:
        raise HTTPException(status_code=500, detail="item_policy_missing:lot_source_policy")
    if snapshot["item_expiry_policy_snapshot"] is None:
        raise HTTPException(status_code=500, detail="item_policy_missing:expiry_policy")

    # ---------------------------
    # 构造 identity 查询
    # ---------------------------
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

    # ---------------------------
    # 若已存在
    # ---------------------------
    if existing:
        if lot_code_source == "INTERNAL":
            return existing.id

        # SUPPLIER 需要校验 snapshot 一致性
        if not _snapshot_equal(existing, snapshot):
            raise HTTPException(status_code=409, detail="lot_snapshot_conflict")

        return existing.id

    # ---------------------------
    # 不存在 → 创建
    # ---------------------------
    new_lot = Lot(
        warehouse_id=warehouse_id,
        item_id=item.id,
        lot_code_source=lot_code_source,
        lot_code=lot_code,
        source_receipt_id=source_receipt_id,
        source_line_no=source_line_no,
        production_date=production_date,
        expiry_date=expiry_date,
        expiry_source=expiry_source,
        shelf_life_days_applied=shelf_life_days_applied,
        item_has_shelf_life_snapshot=snapshot["item_has_shelf_life_snapshot"],
        item_shelf_life_value_snapshot=snapshot["item_shelf_life_value_snapshot"],
        item_shelf_life_unit_snapshot=snapshot["item_shelf_life_unit_snapshot"],
        item_uom_snapshot=snapshot["item_uom_snapshot"],
        item_case_ratio_snapshot=snapshot["item_case_ratio_snapshot"],
        item_case_uom_snapshot=snapshot["item_case_uom_snapshot"],
        # Phase M policy snapshots
        item_lot_source_policy_snapshot=snapshot["item_lot_source_policy_snapshot"],
        item_expiry_policy_snapshot=snapshot["item_expiry_policy_snapshot"],
        item_derivation_allowed_snapshot=snapshot["item_derivation_allowed_snapshot"],
        item_uom_governance_enabled_snapshot=snapshot["item_uom_governance_enabled_snapshot"],
    )

    db.add(new_lot)

    try:
        await db.flush()
        return new_lot.id

    except IntegrityError:
        await db.rollback()
        # 并发情况下重新查
        result = await db.execute(stmt)
        existing = result.scalar_one()

        if lot_code_source == "SUPPLIER":
            if not _snapshot_equal(existing, snapshot):
                raise HTTPException(status_code=409, detail="lot_snapshot_conflict")

        return existing.id
