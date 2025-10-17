import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.snapshot_service import SnapshotService

pytestmark = pytest.mark.asyncio


async def _seed(session: AsyncSession):
    # items（写入 sku 以满足 NOT NULL）
    await session.execute(
        text(
            """
        INSERT INTO items(id, sku, name)
        VALUES (100, 'ITEM-100', '猫粮1.5kg')
        ON CONFLICT (id) DO UPDATE SET sku=EXCLUDED.sku, name=EXCLUDED.name
    """
        )
    )
    await session.execute(
        text(
            """
        INSERT INTO items(id, sku, name)
        VALUES (101, 'ITEM-101', '冻干鸡胸')
        ON CONFLICT (id) DO UPDATE SET sku=EXCLUDED.sku, name=EXCLUDED.name
    """
        )
    )

    # locations
    await session.execute(
        text(
            """
        INSERT INTO locations(id, warehouse_id, name)
        VALUES (11, 1, 'A1') ON CONFLICT (id) DO NOTHING
    """
        )
    )
    await session.execute(
        text(
            """
        INSERT INTO locations(id, warehouse_id, name)
        VALUES (12, 1, 'B2') ON CONFLICT (id) DO NOTHING
    """
        )
    )
    await session.execute(
        text(
            """
        INSERT INTO locations(id, warehouse_id, name)
        VALUES (13, 1, 'STAGE') ON CONFLICT (id) DO NOTHING
    """
        )
    )

    # stocks: item 100 在 A1×60, B2×40；item 101 在 STAGE×5
    await session.execute(
        text(
            """
        INSERT INTO stocks(item_id, location_id, qty) VALUES
        (100,11,60),(100,12,40),(101,13,5)
        ON CONFLICT (item_id, location_id) DO UPDATE SET qty = EXCLUDED.qty
    """
        )
    )

    # 批次（可选）：给 item 100 一个未来到期日；item 101 无批次也可
    await session.execute(
        text(
            """
        INSERT INTO batches(item_id, warehouse_id, location_id, batch_code, production_date, expiry_date, qty)
        VALUES (100, 1, 11, 'B-FOO', DATE '2025-09-01', DATE '2026-09-01', 10)
        ON CONFLICT DO NOTHING
    """
        )
    )


async def test_snapshot_inventory_min(session: AsyncSession):
    # 用同一事务保存点写入种子
    async with session.begin_nested():
        await _seed(session)

    # 直接调用 Service（非分页旧口径）
    data = await SnapshotService.query_inventory_snapshot(session)
    by_id = {d["item_id"]: d for d in data}

    # item 100：总量 100，Top2 A1×60, B2×40（按 qty 降序）
    i100 = by_id[100]
    assert i100["total_qty"] == 100
    top = i100["top2_locations"]
    assert isinstance(top, list) and len(top) == 2
    assert top[0]["qty"] == 60 and top[1]["qty"] == 40

    # item 101：总量 5，Top2 只有一条 STAGE×5
    i101 = by_id[101]
    assert i101["total_qty"] == 5
    top2 = i101["top2_locations"]
    assert len(top2) == 1 and top2[0]["qty"] == 5

    # earliest_expiry：item 100 有日期；near_expiry（默认 30 天）布尔值即可
    assert i100["earliest_expiry"] is not None
    assert i100["near_expiry"] in (True, False)


async def test_snapshot_inventory_paged_search(session: AsyncSession):
    """
    直接用 Service 的分页/搜索接口（共享同一个 session），
    避免 http 客户端使用独立会话看不到未提交数据。
    """
    async with session.begin_nested():
        await _seed(session)

    js = await SnapshotService.query_inventory_snapshot_paged(
        session=session, q="猫粮", offset=0, limit=1
    )
    assert js["total"] >= 1
    assert js["limit"] == 1
    assert len(js["rows"]) == 1
    row = js["rows"][0]
    assert "item_id" in row and "total_qty" in row and "top2_locations" in row
    assert "猫粮" in row["item_name"]
