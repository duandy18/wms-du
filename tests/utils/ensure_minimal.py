# tests/utils/ensure_minimal.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ---------- helpers ----------
async def _sync_locations_seq(session: AsyncSession) -> None:
    """
    将 locations_id_seq 的“下一次取值”同步到 MAX(id)+1，避免主键撞车。
    幂等可重复执行；不消耗 nextval。
    """
    await session.execute(
        text(
            """
        DO $$
        DECLARE maxid bigint;
        BEGIN
          SELECT COALESCE(MAX(id),0) INTO maxid FROM public.locations;
          PERFORM setval('public.locations_id_seq', GREATEST(maxid+1,1), false);
        END$$;
        """
        )
    )


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


# ---------- locations ----------
async def ensure_location(
    session: AsyncSession,
    *,
    id: Optional[int] = None,
    warehouse_id: int,
    code: str,
    name: Optional[str] = None,
) -> int:
    """
    优先走“无 id 自动取号”路径；必要时也支持显式 id（显式写后自动同步序列）。
    返回该 location 的 id。
    """
    name = name or code
    await ensure_warehouse(session, id=warehouse_id)

    if id is None:
        ins = await session.execute(
            text(
                """
                INSERT INTO locations (warehouse_id, code, name)
                VALUES (:wid, :code, :name)
                ON CONFLICT (warehouse_id, code) DO NOTHING
                RETURNING id
            """
            ),
            {"wid": warehouse_id, "code": code, "name": name},
        )
        new_id = ins.scalar()
        if new_id is None:
            row = await session.execute(
                text("SELECT id FROM locations WHERE warehouse_id=:wid AND code=:code LIMIT 1"),
                {"wid": warehouse_id, "code": code},
            )
            got = row.scalar()
            if got is None:
                raise RuntimeError("ensure_location failed to resolve id")
            return int(got)
        return int(new_id)

    await session.execute(
        text(
            """
            INSERT INTO locations (id, warehouse_id, code, name)
            VALUES (:id, :wid, :code, :name)
            ON CONFLICT (id) DO NOTHING
        """
        ),
        {"id": int(id), "wid": warehouse_id, "code": code, "name": name},
    )
    await _sync_locations_seq(session)

    return int(id)


# ---------- items ----------
async def ensure_item(
    session: AsyncSession, *, id: int, sku: Optional[str] = None, name: Optional[str] = None
) -> None:
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
async def ensure_batch(session: AsyncSession, *, item_id: int, location_id: int, batch_code: str) -> None:
    """
    基于当前口径创建批次主档：
    - warehouse_id 由 locations 推导；
    - batches 唯一维度： (item_id, warehouse_id, batch_code)
    """
    await session.execute(
        text(
            """
            INSERT INTO batches (item_id, warehouse_id, batch_code)
            SELECT :item, l.warehouse_id, :code
              FROM locations l
             WHERE l.id = :loc
            ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
        """
        ),
        {"item": int(item_id), "loc": int(location_id), "code": str(batch_code)},
    )


async def ensure_stock_slot(session: AsyncSession, *, item_id: int, location_id: int, batch_code: str) -> None:
    """
    创建 stocks 槽位（旧测试工具，尽量保持行为）：

    注意：当前 stocks 的唯一约束已经迁移为 uq_stocks_item_wh_batch（item_id, warehouse_id, batch_code_key）。
    这里仍通过 batches 找到 warehouse_id，再插入 stocks 3D 槽位。
    """
    await session.execute(
        text(
            """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
            SELECT :item, b.warehouse_id, b.batch_code, 0
              FROM batches b
             WHERE b.item_id=:item AND b.batch_code=:code
             LIMIT 1
            ON CONFLICT ON CONSTRAINT uq_stocks_item_wh_batch DO NOTHING
        """
        ),
        {"item": int(item_id), "loc": int(location_id), "code": str(batch_code)},
    )


async def set_stock_qty(
    session: AsyncSession, *, item_id: int, location_id: int, batch_code: str, qty: int
) -> None:
    """
    把 stocks 槽位的 qty 设置为特定值（幂等重置，用于测试）
    """
    await session.execute(
        text(
            """
            UPDATE stocks s
               SET qty = :q
              FROM batches b
             WHERE s.item_id = b.item_id
               AND s.warehouse_id = b.warehouse_id
               AND s.batch_code IS NOT DISTINCT FROM b.batch_code
               AND b.item_id=:item AND b.batch_code=:code
        """
        ),
        {"q": int(qty), "item": int(item_id), "loc": int(location_id), "code": str(batch_code)},
    )


async def ensure_batch_with_stock(
    session: AsyncSession,
    *,
    item_id: int,
    location_id: int,
    warehouse_id: int,
    batch_code: str,
    qty: int,
) -> None:
    """
    组合式工具：补齐依赖 → item / location / batch / stock 槽位，然后把 qty 设置到目标值。
    """
    await ensure_item(session, id=item_id)
    loc_id = await ensure_location(session, id=location_id, warehouse_id=warehouse_id, code=f"LOC-{location_id}")
    await ensure_batch(session, item_id=item_id, location_id=loc_id, batch_code=batch_code)
    await ensure_stock_slot(session, item_id=item_id, location_id=loc_id, batch_code=batch_code)
    await set_stock_qty(session, item_id=item_id, location_id=loc_id, batch_code=batch_code, qty=qty)
