import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.snapshot_service import SnapshotService

pytestmark = pytest.mark.asyncio


async def _seed(session: AsyncSession) -> None:
    """
    v2 口径种子数据：

    - items: 100 / 101
    - warehouses: 1
    - stocks: (wh=1, item=100, batch 'B-A1'×60 + batch 'B-B2'×40；
               wh=1, item=101, batch 'B-STAGE'×5)
    - batches: 给 item 100 的两个批次加一个未来 expiry_date，item 101 无过期日也可以
    """

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

    # warehouse（v2 核心维度）
    await session.execute(
        text(
            """
            INSERT INTO warehouses (id, name)
            VALUES (1, 'WH-1')
            ON CONFLICT (id) DO NOTHING
            """
        )
    )

    # 批次：给 item 100 两个批次，带 expiry_date；item 101 一个批次即可
    await session.execute(
        text(
            """
            INSERT INTO batches (item_id, warehouse_id, batch_code, expiry_date)
            VALUES
              (100, 1, 'B-A1',    DATE '2026-09-01'),
              (100, 1, 'B-B2',    DATE '2026-10-01'),
              (101, 1, 'B-STAGE', NULL)
            ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
            """
        )
    )

    # stocks: v2 粒度 (item_id, warehouse_id, batch_code, qty)
    # item 100：A1×60, B2×40；item 101：STAGE×5
    await session.execute(
        text(
            """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty) VALUES
              (100, 1, 'B-A1',    60),
              (100, 1, 'B-B2',    40),
              (101, 1, 'B-STAGE', 5)
            ON CONFLICT (item_id, warehouse_id, batch_code)
            DO UPDATE SET qty = EXCLUDED.qty
            """
        )
    )


async def test_snapshot_inventory_min(session: AsyncSession):
    """
    核心验证：

    - total_qty 按 item 汇总；
    - "top2_locations" 字段保留名称，但语义为“代表性明细”，这里只关心 qty 排序；
    - earliest_expiry / near_expiry 仍然有值，但不过分绑定具体日期。
    """
    async with session.begin_nested():
        await _seed(session)

    data = await SnapshotService.query_inventory_snapshot(session)
    by_id = {d["item_id"]: d for d in data}

    # item 100：总量 100，Top2 60 / 40（按 qty 降序）
    i100 = by_id[100]
    assert i100["total_qty"] == 100
    top = i100["top2_locations"]
    assert isinstance(top, list) and len(top) == 2
    assert top[0]["qty"] == 60 and top[1]["qty"] == 40

    # item 101：总量 5，Top2 只有一条 5
    i101 = by_id[101]
    assert i101["total_qty"] == 5
    top2 = i101["top2_locations"]
    assert len(top2) == 1 and top2[0]["qty"] == 5

    # earliest_expiry：item 100 有日期；near_expiry（默认 30 天）布尔值即可
    assert i100.get("earliest_expiry") is not None
    assert i100.get("near_expiry") in (True, False)


async def test_snapshot_inventory_paged_search(session: AsyncSession):
    """
    验证分页 + 模糊搜索：

    - 通过 q="猫粮" 搜到 item 100；
    - 限制 limit=1；
    - rows 中的字段齐全。
    """
    async with session.begin_nested():
        await _seed(session)

    js = await SnapshotService.query_inventory_snapshot_paged(
        session=session,
        q="猫粮",
        offset=0,
        limit=1,
    )
    assert js["total"] >= 1
    assert js["limit"] == 1
    assert len(js["rows"]) == 1
    row = js["rows"][0]
    assert "item_id" in row and "total_qty" in row and "top2_locations" in row
    assert "猫粮" in row["item_name"]
