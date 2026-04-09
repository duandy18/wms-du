# app/wms/stock/services/lot_service.py
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lot import Lot
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
    source_receipt_id: Optional[int],
    source_line_no: Optional[int],
) -> int:
    """
    兼容层 lot 创建/解析（Phase M-5）：

    终态收口：
    - SUPPLIER lot 统一走 ensure_lot_full（写 lot_code_key 防漂移）
    - INTERNAL lot 统一走 ensure_internal_lot_singleton（按 wh+item 单例）
    - 本模块不再直接 new Lot()/flush，避免第二入口造成漂移与约束冲突
    - 跨域输入不再接收 Item ORM，而是接收 PMS public ItemPolicy
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

        # ensure supplier lot by key (drift-proof)
        lot_id = await ensure_lot_full(
            db,
            item_id=int(item_policy.item_id),
            warehouse_id=int(warehouse_id),
            lot_code=str(lot_code),
            production_date=None,
            expiry_date=None,
        )

        # read back to verify snapshot compatibility (historical freeze)
        stmt = select(Lot).where(Lot.id == int(lot_id))
        existing = (await db.execute(stmt)).scalars().first()
        if existing is None:
            raise HTTPException(status_code=500, detail="lot_create_or_resolve_failed")

        if not _snapshot_equal(existing, snapshot):
            raise HTTPException(status_code=409, detail="lot_snapshot_conflict")
        return int(existing.id)

    # INTERNAL: singleton per (warehouse,item); provenance optional but paired
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
        # internal provenance pair violated
        raise HTTPException(status_code=422, detail=str(e)) from e
