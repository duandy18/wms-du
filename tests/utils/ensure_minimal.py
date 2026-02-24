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
        {"id": id, "name": name},
    )


# ---------- items ----------
async def ensure_item(session: AsyncSession, *, id: int, sku: Optional[str] = None, name: Optional[str] = None) -> None:
    """
    items 表：sku NOT NULL, name NOT NULL。
    自动生成 SKU/name 以防缺失。
    """
    sku = sku or f"SKU-{id}"
    name = name or f"ITEM-{id}"
    await session.execute(
        text(
            """
            INSERT INTO items (id, sku, name)
            VALUES (:id, :sku, :name)
            ON CONFLICT (id) DO UPDATE
            SET sku = EXCLUDED.sku, name = EXCLUDED.name
        """
        ),
        {"id": id, "sku": sku, "name": name},
    )


# ---------- batches / stocks ----------
async def ensure_batch(session: AsyncSession, *, item_id: int, warehouse_id: int, batch_code: str) -> None:
    """
    基于当前口径创建批次主档：
    - batches 唯一维度： (item_id, warehouse_id, batch_code)
    """
    await session.execute(
        text(
            """
            INSERT INTO batches (item_id, warehouse_id, batch_code)
            VALUES (:item, :wid, :code)
            ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
        """
        ),
        {"item": int(item_id), "wid": int(warehouse_id), "code": str(batch_code)},
    )


async def ensure_stock_slot(session: AsyncSession, *, item_id: int, warehouse_id: int, batch_code: str | None) -> None:
    """
    创建 stocks 槽位（测试工具）：
    唯一约束 uq_stocks_item_wh_batch（item_id, warehouse_id, batch_code_key）
    """
    await session.execute(
        text(
            """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
            VALUES (:item, :wid, :code, 0)
            ON CONFLICT ON CONSTRAINT uq_stocks_item_wh_batch DO NOTHING
        """
        ),
        {"item": int(item_id), "wid": int(warehouse_id), "code": batch_code},
    )


async def set_stock_qty(session: AsyncSession, *, item_id: int, warehouse_id: int, batch_code: str | None, qty: int) -> None:
    """
    把 stocks 槽位的 qty 设置为特定值（幂等重置，用于测试）
    """
    await session.execute(
        text(
            """
            UPDATE stocks
               SET qty = :q
             WHERE item_id=:item
               AND warehouse_id=:wid
               AND batch_code IS NOT DISTINCT FROM :code
        """
        ),
        {"q": int(qty), "item": int(item_id), "wid": int(warehouse_id), "code": batch_code},
    )


async def ensure_batch_with_stock(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str,
    qty: int,
) -> None:
    """
    组合式工具：补齐依赖 → item / warehouse / batch / stock 槽位，然后把 qty 设置到目标值。
    """
    await ensure_item(session, id=item_id)
    await ensure_warehouse(session, id=warehouse_id)
    await ensure_batch(session, item_id=item_id, warehouse_id=warehouse_id, batch_code=batch_code)
    await ensure_stock_slot(session, item_id=item_id, warehouse_id=warehouse_id, batch_code=batch_code)
    await set_stock_qty(session, item_id=item_id, warehouse_id=warehouse_id, batch_code=batch_code, qty=qty)
