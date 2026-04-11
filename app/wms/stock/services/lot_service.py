# app/wms/stock/services/lot_service.py
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.stock.models.lot import Lot
from app.pms.public.items.contracts.item_policy import ItemPolicy
from app.wms.stock.services.lots import ensure_internal_lot_singleton, ensure_lot_full


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
    item_policy: ItemPolicy,
    lot_code_source: str,
    lot_code: Optional[str],
    production_date: Optional[date],
    expiry_date: Optional[date],
    source_receipt_id: Optional[int],
    source_line_no: Optional[int],
) -> int:
    """
    兼容层 lot 创建/解析（Phase M-5）：

    当前中心任务收口：
    - REQUIRED 商品：production_date 是 lot 身份决策输入
    - SUPPLIER lot 仍保留 lot_code 作为展示/追溯属性
    - INTERNAL lot 继续走 singleton（warehouse,item）
    """
    lot_code_source_u = str(lot_code_source or "").upper().strip()
    if lot_code_source_u not in ("SUPPLIER", "INTERNAL"):
        raise HTTPException(status_code=422, detail="invalid_lot_code_source")

    snapshot = {
        "item_shelf_life_value_snapshot": item_policy.shelf_life_value,
        "item_shelf_life_unit_snapshot": item_policy.shelf_life_unit,
        "item_lot_source_policy_snapshot": item_policy.lot_source_policy,
        "item_expiry_policy_snapshot": item_policy.expiry_policy,
        "item_derivation_allowed_snapshot": bool(item_policy.derivation_allowed),
        "item_uom_governance_enabled_snapshot": bool(item_policy.uom_governance_enabled),
    }

    if snapshot["item_lot_source_policy_snapshot"] is None:
        raise HTTPException(status_code=500, detail="item_policy_missing:lot_source_policy")
    if snapshot["item_expiry_policy_snapshot"] is None:
        raise HTTPException(status_code=500, detail="item_policy_missing:expiry_policy")

    if lot_code_source_u == "SUPPLIER":
        if not lot_code or not str(lot_code).strip():
            raise HTTPException(status_code=422, detail="supplier_lot_code_required")

        if str(snapshot["item_expiry_policy_snapshot"]).upper() == "REQUIRED" and production_date is None:
            raise HTTPException(status_code=422, detail="production_date_required_for_required_lot")

        try:
            lot_id = await ensure_lot_full(
                db,
                item_id=int(item_policy.item_id),
                warehouse_id=int(warehouse_id),
                lot_code=str(lot_code),
                production_date=production_date,
                expiry_date=expiry_date,
            )
        except ValueError as e:
            detail = str(e)
            if detail == "supplier_lot_legacy_key_conflict":
                raise HTTPException(status_code=409, detail=detail) from e
            raise HTTPException(status_code=422, detail=detail) from e

        stmt = select(Lot).where(Lot.id == int(lot_id))
        existing = (await db.execute(stmt)).scalars().first()
        if existing is None:
            raise HTTPException(status_code=500, detail="lot_create_or_resolve_failed")

        if not _snapshot_equal(existing, snapshot):
            raise HTTPException(status_code=409, detail="lot_snapshot_conflict")
        return int(existing.id)

    try:
        lot_id2 = await ensure_internal_lot_singleton(
            db,
            item_id=int(item_policy.item_id),
            warehouse_id=int(warehouse_id),
            source_receipt_id=int(source_receipt_id) if source_receipt_id is not None else None,
            source_line_no=int(source_line_no) if source_line_no is not None else None,
        )
        return int(lot_id2)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
