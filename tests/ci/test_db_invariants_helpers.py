"""
CI 基线：数据库不变量（helpers 化）

lot-world 约定（Phase M-5 终态）：

- 库存槽位维度： (item_id, warehouse_id, lot_id)
  * stocks_lot 以 (item_id, warehouse_id, lot_id) 唯一（lot_id 允许为 NULL）
  * 批次展示码：lots.lot_code（SUPPLIER）
  * NULL 槽位：lot_id IS NULL（不使用 lot_id_key=0）

- sum_on_hand 与实际写入一致（按 (item, warehouse) 汇总 stocks_lot.qty）

- 最小连贯性抽检：
  * 至少存在一条 stocks_lot 记录，其 lot_id 指向 lots，
    且 lots 的 (warehouse_id,item_id) 与 stocks_lot 对齐
"""

from __future__ import annotations

import pytest
from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, seed_supplier_lot_slot, sum_on_hand

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_lots_unique_supplier_4d(session: AsyncSession):
    """
    SUPPLIER lot 唯一性（partial unique index）：

    对于同一 (warehouse_id, item_id, lot_code_source='SUPPLIER', lot_code)，重复 seed 只产生一条 lots 记录，
    对应的 stocks_lot 槽位也应只有一条。
    """
    wh, loc, item, code = 1, 1, 99001, "UNI-99001"
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)

    # 复用 seed_supplier_lot_slot：内部会写 lots + stocks_lot（Phase 4E+：不触碰 legacy batches/stocks）
    await seed_supplier_lot_slot(session, item=item, loc=loc, lot_code=code, qty=3, days=365)
    await seed_supplier_lot_slot(session, item=item, loc=loc, lot_code=code, qty=3, days=365)
    await session.commit()

    # lots(SUPPLIER) 中应只有一条记录
    row = await session.execute(
        SA(
            """
            SELECT COUNT(*)
              FROM lots
             WHERE warehouse_id = :w
               AND item_id      = :i
               AND lot_code_source = 'SUPPLIER'
               AND lot_code     = :c
            """
        ),
        {"i": item, "w": wh, "c": code},
    )
    assert int(row.scalar_one()) == 1

    # 对应 stocks_lot 槽位也应唯一（通过 uq_stocks_lot_item_wh_lot 保障）
    row2 = await session.execute(
        SA(
            """
            SELECT COUNT(*)
              FROM stocks_lot sl
              JOIN lots l
                ON l.id = sl.lot_id
             WHERE sl.item_id      = :i
               AND sl.warehouse_id = :w
               AND l.lot_code_source = 'SUPPLIER'
               AND l.lot_code     = :c
            """
        ),
        {"i": item, "w": wh, "c": code},
    )
    assert int(row2.scalar_one()) == 1


@pytest.mark.asyncio
async def test_sum_on_hand_consistency(session: AsyncSession):
    """
    sum_on_hand 与实际写入一致：

    helpers.sum_on_hand 按 (item, warehouse) 汇总的库存值，必须与实际写入相符（stocks_lot）。
    """
    wh, loc, item = 1, 1, 99002
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)

    await seed_supplier_lot_slot(session, item=item, loc=loc, lot_code="Q-99002-A", qty=4, days=365)
    await seed_supplier_lot_slot(session, item=item, loc=loc, lot_code="Q-99002-B", qty=6, days=365)
    await session.commit()

    assert await sum_on_hand(session, item=item, loc=loc) == 10


@pytest.mark.asyncio
async def test_stocks_lot_fk_minimal(session: AsyncSession):
    """
    抽检 stocks_lot → lots / items 的基础连贯性：

    至少存在一条 stocks_lot 记录，其 lot_id 指向 lots，
    且 lots 的 (warehouse_id,item_id) 与 stocks_lot 对齐。
    """
    wh, loc, item = 1, 1, 99003
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)
    await seed_supplier_lot_slot(session, item=item, loc=loc, lot_code="FK-CHK", qty=1, days=365)
    await session.commit()

    row = await session.execute(
        SA(
            """
            SELECT
              sl.item_id,
              l.item_id       AS l_item,
              sl.warehouse_id,
              l.warehouse_id  AS l_wh,
              l.lot_code,
              sl.qty
            FROM stocks_lot sl
            JOIN lots l
              ON l.id = sl.lot_id
            WHERE sl.item_id      = :i
              AND sl.warehouse_id = :w
            LIMIT 1
            """
        ),
        {"i": item, "w": wh},
    )
    rec = row.first()
    assert rec is not None
    item_s, item_l, wh_s, wh_l, code, qty = rec
    assert item_s == item_l
    assert wh_s == wh_l
    assert isinstance(code, str) and code
    assert int(qty) >= 0
