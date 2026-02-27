# tests/utils/ensure_minimal.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ---------- warehouses ----------
async def ensure_warehouse(session: AsyncSession, *, id: int, name: Optional[str] = None) -> None:
    name = name or f"WH-{id}"
    await session.execute(
        text(
            """
            INSERT INTO warehouses (id, name)
            VALUES (:id, :name)
            ON CONFLICT (id) DO NOTHING
        """
        ),
        {"id": int(id), "name": str(name)},
    )


# ---------- items ----------
async def ensure_item(
    session: AsyncSession,
    *,
    id: int,
    sku: Optional[str] = None,
    name: Optional[str] = None,
    uom: Optional[str] = None,
    expiry_required: bool = False,
) -> None:
    """
    items 表（Phase M）：
    - sku NOT NULL, name NOT NULL
    - uom（通常 NOT NULL；测试侧必须显式给，避免依赖默认）
    - lot_source_policy / expiry_policy / derivation_allowed / uom_governance_enabled 均 NOT NULL 且无默认
    - has_shelf_life 是镜像字段（DB CHECK 锁死：has_shelf_life == expiry_policy=='REQUIRED'）

    测试工具：用最小但合法的默认 policy，避免各种 helper 插 lot 时爆 NOT NULL。

    使用方式：
    - 默认（无保质期）：expiry_required=False -> expiry_policy='NONE', has_shelf_life=FALSE
    - 需要保质期：expiry_required=True  -> expiry_policy='REQUIRED', has_shelf_life=TRUE
    """
    sku = sku or f"SKU-{id}"
    name = name or f"ITEM-{id}"
    uom = uom or "PCS"

    expiry_policy = "REQUIRED" if expiry_required else "NONE"
    has_shelf_life = bool(expiry_required)

    await session.execute(
        text(
            """
            INSERT INTO items (
              id, sku, name, uom,
              lot_source_policy, expiry_policy, derivation_allowed, uom_governance_enabled,
              has_shelf_life
            )
            VALUES (
              :id, :sku, :name, :uom,
              'SUPPLIER_ONLY'::lot_source_policy, CAST(:expiry_policy AS expiry_policy), TRUE, FALSE,
              CAST(:has_shelf_life AS boolean)
            )
            ON CONFLICT (id) DO UPDATE
               SET sku = EXCLUDED.sku,
                   name = EXCLUDED.name,
                   uom = EXCLUDED.uom,
                   lot_source_policy = EXCLUDED.lot_source_policy,
                   expiry_policy = EXCLUDED.expiry_policy,
                   derivation_allowed = EXCLUDED.derivation_allowed,
                   uom_governance_enabled = EXCLUDED.uom_governance_enabled,
                   has_shelf_life = EXCLUDED.has_shelf_life
            """
        ),
        {
            "id": int(id),
            "sku": str(sku),
            "name": str(name),
            "uom": str(uom),
            "expiry_policy": str(expiry_policy),
            "has_shelf_life": bool(has_shelf_life),
        },
    )


# ---------- lots / stocks_lot ----------
async def ensure_supplier_lot(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_code: str,
) -> int:
    """
    Phase 4D：创建/获取一个最小合法 SUPPLIER lot，并返回 lot_id。

    注意：
    - lots 的 SUPPLIER 唯一性是 partial unique index，不是 constraint
    - 使用 ON CONFLICT (cols) WHERE predicate 形式
    - lots 对策略快照（item_*_snapshot）有 NOT NULL 护栏 → 必须从 items 真相源读取并冻结
    """
    code = str(lot_code).strip()
    if not code:
        raise ValueError("lot_code empty")

    row = (
        await session.execute(
            text(
                """
                INSERT INTO lots(
                    warehouse_id,
                    item_id,
                    lot_code_source,
                    lot_code,
                    source_receipt_id,
                    source_line_no,
                    production_date,
                    expiry_date,
                    expiry_source,
                    -- required snapshots (NOT NULL)
                    item_lot_source_policy_snapshot,
                    item_expiry_policy_snapshot,
                    item_derivation_allowed_snapshot,
                    item_uom_governance_enabled_snapshot,
                    -- optional snapshots (nullable)
                    item_has_shelf_life_snapshot,
                    item_shelf_life_value_snapshot,
                    item_shelf_life_unit_snapshot,
                    item_uom_snapshot,
                    item_case_ratio_snapshot,
                    item_case_uom_snapshot
                )
                SELECT
                    :w,
                    :i,
                    'SUPPLIER',
                    :code,
                    NULL,
                    NULL,
                    CURRENT_DATE,
                    CURRENT_DATE + INTERVAL '365 day',
                    'EXPLICIT',
                    it.lot_source_policy,
                    it.expiry_policy,
                    it.derivation_allowed,
                    it.uom_governance_enabled,
                    it.has_shelf_life,
                    it.shelf_life_value,
                    it.shelf_life_unit,
                    it.uom,
                    it.case_ratio,
                    it.case_uom
                  FROM items it
                 WHERE it.id = :i
                ON CONFLICT (warehouse_id, item_id, lot_code_source, lot_code)
                WHERE lot_code_source = 'SUPPLIER'
                DO UPDATE SET expiry_date = EXCLUDED.expiry_date
                RETURNING id
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "code": code},
        )
    ).first()
    if not row:
        raise ValueError(f"failed to ensure lot for wh={warehouse_id}, item={item_id}, code={lot_code}")
    return int(row[0])


async def ensure_stock_slot(session: AsyncSession, *, item_id: int, warehouse_id: int, batch_code: str | None) -> None:
    """
    Phase 4D：创建 stocks_lot 槽位（测试工具）。

    batch_code 语义：
    - None：lot_id=NULL（lot_id_key=0 槽位）
    - 非空：作为 SUPPLIER lot_code，映射到 lots.id
    """
    if batch_code is None:
        await session.execute(
            text(
                """
                INSERT INTO stocks_lot (item_id, warehouse_id, lot_id, qty)
                VALUES (:i, :w, NULL, 0)
                ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot
                DO NOTHING
                """
            ),
            {"i": int(item_id), "w": int(warehouse_id)},
        )
        return

    lot_id = await ensure_supplier_lot(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_code=str(batch_code),
    )
    await session.execute(
        text(
            """
            INSERT INTO stocks_lot (item_id, warehouse_id, lot_id, qty)
            VALUES (:i, :w, :lot, 0)
            ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot
            DO NOTHING
            """
        ),
        {"i": int(item_id), "w": int(warehouse_id), "lot": int(lot_id)},
    )


async def set_stock_qty(session: AsyncSession, *, item_id: int, warehouse_id: int, batch_code: str | None, qty: int) -> None:
    """
    Phase 4D：把 stocks_lot 槽位的 qty 设置为特定值（幂等重置，用于测试）。
    """
    if batch_code is None:
        await session.execute(
            text(
                """
                UPDATE stocks_lot
                   SET qty = :q
                 WHERE item_id = :i
                   AND warehouse_id = :w
                   AND lot_id IS NULL
                """
            ),
            {"q": int(qty), "i": int(item_id), "w": int(warehouse_id)},
        )
        return

    lot_id = await ensure_supplier_lot(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_code=str(batch_code),
    )
    await session.execute(
        text(
            """
            UPDATE stocks_lot
               SET qty = :q
             WHERE item_id = :i
               AND warehouse_id = :w
               AND lot_id = :lot
            """
        ),
        {"q": int(qty), "i": int(item_id), "w": int(warehouse_id), "lot": int(lot_id)},
    )


# ---------- legacy-named helpers (kept for compatibility) ----------
async def ensure_batch(session: AsyncSession, *, item_id: int, warehouse_id: int, batch_code: str) -> None:
    """
    兼容旧测试命名：ensure_batch -> 现在等价于 ensure_supplier_lot（lot-world）。
    """
    _ = await ensure_supplier_lot(session, item_id=int(item_id), warehouse_id=int(warehouse_id), lot_code=str(batch_code))


async def ensure_batch_with_stock(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str,
    qty: int,
) -> None:
    """
    组合式工具：补齐依赖 → item / warehouse / lot / stocks_lot 槽位，然后把 qty 设置到目标值。
    """
    await ensure_item(session, id=int(item_id))
    await ensure_warehouse(session, id=int(warehouse_id))
    await ensure_batch(session, item_id=int(item_id), warehouse_id=int(warehouse_id), batch_code=str(batch_code))
    await ensure_stock_slot(session, item_id=int(item_id), warehouse_id=int(warehouse_id), batch_code=str(batch_code))
    await set_stock_qty(session, item_id=int(item_id), warehouse_id=int(warehouse_id), batch_code=str(batch_code), qty=int(qty))
