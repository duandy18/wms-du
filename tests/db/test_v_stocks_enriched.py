import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.contract


async def _ensure_wh_and_loc(session: AsyncSession) -> int:
    """
    幂等创建/获取: 仓库 id=1；测试专用库位 code='LOC-ENRICH'（不写 id，交给序列）。
    返回该库位的实际 id。
    """
    # 仓库
    await session.execute(
        text("INSERT INTO warehouses (id, name) VALUES (1, 'WH-1') ON CONFLICT (id) DO NOTHING")
    )

    # 专用库位（自然键幂等）
    ins = await session.execute(
        text(
            """
            INSERT INTO locations (warehouse_id, code, name)
            VALUES (1, 'LOC-ENRICH', 'LOC-ENRICH')
            ON CONFLICT (warehouse_id, code) DO NOTHING
            RETURNING id
            """
        )
    )
    loc_id = ins.scalar()
    if loc_id is None:
        row = await session.execute(
            text("SELECT id FROM locations WHERE warehouse_id=1 AND code='LOC-ENRICH' LIMIT 1")
        )
        loc_id = row.scalar_one()
    return int(loc_id)


async def _ensure_item(session: AsyncSession, item_id=606):
    await session.execute(
        text(
            """
            INSERT INTO items (id, sku, name, unit, shelf_life_days)
            VALUES (:i, :sku, :name, 'EA', 0)
            ON CONFLICT (id) DO UPDATE SET sku=EXCLUDED.sku, name=EXCLUDED.name
            """
        ),
        {"i": item_id, "sku": f"SKU-{item_id}", "name": f"DEMO-{item_id}"},
    )


async def _upsert_batch_and_stock(
    session: AsyncSession, *, item_id: int, loc_id: int, code: str, qty: int
):
    # 批次（由 locations 推导仓库）
    await session.execute(
        text(
            """
            INSERT INTO batches (item_id, warehouse_id, batch_code)
            SELECT :i, l.warehouse_id, :loc, :code
              FROM locations l
             WHERE l.id=:loc
            ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
            """
        ),
        {"i": item_id, "loc": loc_id, "code": code},
    )

    # 槽位（item+loc+batch 唯一），先建 0，再设定数量
    await session.execute(
        text(
            """
            INSERT INTO stocks (item_id, location_id, batch_id, qty)
            SELECT :i, :loc, b.id, 0
              FROM batches b
             WHERE b.item_id=:i   AND b.batch_code=:code
            ON CONFLICT ON CONSTRAINT uq_stocks_item_loc_batch DO NOTHING
            """
        ),
        {"i": item_id, "loc": loc_id, "code": code},
    )
    await session.execute(
        text(
            """
            UPDATE stocks s
               SET qty = :q
              FROM batches b
             WHERE s.batch_id=b.id
               AND b.item_id=:i   AND b.batch_code=:code
            """
        ),
        {"q": qty, "i": item_id, "loc": loc_id, "code": code},
    )


@pytest.mark.asyncio
async def test_v_stocks_enriched_fields(session: AsyncSession):
    # 1) 基线：仓库 + 专用库位
    loc_id = await _ensure_wh_and_loc(session)

    # 2) 专用商品 + 批次 + 库存
    await _ensure_item(session, item_id=606)
    await _upsert_batch_and_stock(session, item_id=606, loc_id=loc_id, code="B-ENRICH", qty=9)

    # 3) 视图校验（用专用库位，不再查询 location=1）
    row = await session.execute(
        text(
            """
            SELECT item_id, location_id, batch_id, qty, batch_code, warehouse_id
              FROM v_stocks_enriched
             WHERE item_id=606 AND location_id=:loc AND batch_code='B-ENRICH'
             LIMIT 1
            """
        ),
        {"loc": loc_id},
    )
    got = row.mappings().first()
    assert got is not None, "v_stocks_enriched 没有返回该槽位"
    # 字段来源校验：batch_code 来自 batches；warehouse_id 来自 locations
    assert got["batch_code"] == "B-ENRICH"
    assert got["warehouse_id"] == 1
    assert got["qty"] == 9
