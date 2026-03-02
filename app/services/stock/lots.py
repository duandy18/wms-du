# app/services/stock/lots.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_lot_full(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_code: str,
    production_date,
    expiry_date,
) -> int:
    """
    Phase 4E（真收口）：
    - 批次主档统一迁移到 lots（SUPPLIER lot）
    - 返回 lot_id（幂等）

    Phase M-5（结构治理：unit_governance 二阶段）：
    - lots 不承载 production/expiry 时间事实（时间真相在 stock_ledger）
    - lots 的单位快照列已移除（不再写入 base/purchase uom snapshot）
      单位展示/推导应来自 item_uoms（结构层）与业务行快照（PO/Receipt）
    """
    _ = production_date
    _ = expiry_date

    code = str(lot_code).strip()
    if not code:
        raise ValueError("lot_code empty")

    row = await session.execute(
        text(
            """
            INSERT INTO lots(
                warehouse_id,
                item_id,
                lot_code_source,
                lot_code,
                source_receipt_id,
                source_line_no,
                -- required snapshots (NOT NULL)
                item_lot_source_policy_snapshot,
                item_expiry_policy_snapshot,
                item_derivation_allowed_snapshot,
                item_uom_governance_enabled_snapshot,
                -- optional snapshots (nullable)
                item_shelf_life_value_snapshot,
                item_shelf_life_unit_snapshot
            )
            SELECT
                :w,
                :i,
                'SUPPLIER',
                :code,
                NULL,
                NULL,
                it.lot_source_policy,
                it.expiry_policy,
                it.derivation_allowed,
                it.uom_governance_enabled,
                it.shelf_life_value,
                it.shelf_life_unit
              FROM items it
             WHERE it.id = :i
            ON CONFLICT (warehouse_id, item_id, lot_code)
            WHERE lot_code IS NOT NULL
            DO NOTHING
            RETURNING id
            """
        ),
        {
            "w": int(warehouse_id),
            "i": int(item_id),
            "code": code,
        },
    )
    got = row.scalar_one_or_none()
    if got is not None:
        return int(got)

    row2 = await session.execute(
        text(
            """
            SELECT id
              FROM lots
             WHERE warehouse_id = :w
               AND item_id      = :i
               AND lot_code_source = 'SUPPLIER'
               AND lot_code     = :code
             LIMIT 1
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "code": code},
    )
    got2 = row2.scalar_one_or_none()
    if got2 is None:
        raise RuntimeError("ensure_lot_full failed to materialize lot row")
    return int(got2)


async def ensure_batch_full(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str,
    production_date,
    expiry_date,
) -> int:
    return await ensure_lot_full(
        session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        lot_code=batch_code,
        production_date=production_date,
        expiry_date=expiry_date,
    )
