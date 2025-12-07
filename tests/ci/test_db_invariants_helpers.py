"""
CI 基线：数据库不变量（helpers 化）

当前模型约定（Phase 3.x）：

- 批次槽位维度： (item_id, warehouse_id, batch_code)
  * 不再使用 location_id 参与唯一键
  * batches 与 stocks 均以该三元组作为逻辑槽位

- sum_on_hand 与实际写入一致（按 (item, warehouse) 汇总）

- stocks 外键/约束最小连贯性抽检：
  * 至少存在一条 stocks，其 (item_id, warehouse_id, batch_code)
    能与 batches 对齐
"""

from __future__ import annotations

import pytest
from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, seed_batch_slot, sum_on_hand

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_batches_unique_3d(session: AsyncSession):
    """
    批次槽位唯一性（3 维）：

    对于同一 (item_id, warehouse_id, batch_code)，重复 seed 只产生一条 batches 记录，
    对应的 stocks 槽位也应只有一条。
    """
    wh, loc, item, code = 1, 1, 99001, "UNI-99001"
    # helpers 仍使用 loc 参数，但在新模型中 loc 即 warehouse_id
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)

    # 同一槽位两次插入，第二次幂等，无重复
    await seed_batch_slot(session, item=item, loc=loc, code=code, qty=3, days=365)
    await seed_batch_slot(session, item=item, loc=loc, code=code, qty=3, days=365)
    await session.commit()

    # batches 中应只有一条记录
    row = await session.execute(
        SA(
            """
           SELECT COUNT(*) FROM batches
            WHERE item_id = :i
              AND warehouse_id = :w
              AND batch_code = :c
        """
        ),
        {"i": item, "w": wh, "c": code},
    )
    assert int(row.scalar_one()) == 1

    # 对应 stocks 槽位也应唯一：
    # 以 (item_id, warehouse_id, batch_code) 为槽位维度，
    # stocks 与 batches 在该三元组上应可一一对应。
    row2 = await session.execute(
        SA(
            """
           SELECT COUNT(*)
             FROM stocks s
             JOIN batches b
               ON b.item_id      = s.item_id
              AND b.warehouse_id = s.warehouse_id
              AND b.batch_code   = s.batch_code
            WHERE b.item_id      = :i
              AND b.warehouse_id = :w
              AND b.batch_code   = :c
        """
        ),
        {"i": item, "w": wh, "c": code},
    )
    assert int(row2.scalar_one()) == 1


@pytest.mark.asyncio
async def test_sum_on_hand_consistency(session: AsyncSession):
    """
    sum_on_hand 与实际写入一致：

    helpers.sum_on_hand 按 (item, warehouse) 汇总的库存值，必须与实际写入相符。
    """
    wh, loc, item = 1, 1, 99002
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)

    await seed_batch_slot(session, item=item, loc=loc, code="Q-99002-A", qty=4, days=365)
    await seed_batch_slot(session, item=item, loc=loc, code="Q-99002-B", qty=6, days=365)
    await session.commit()

    # sum_on_hand 应为 10
    assert await sum_on_hand(session, item=item, loc=loc) == 10


@pytest.mark.asyncio
async def test_stocks_fk_minimal(session: AsyncSession):
    """
    抽检 stocks → batches / items 的基础连贯性：

    至少存在一条 stocks 记录，其 (item_id, warehouse_id, batch_code)
    能与 batches 中对应记录对齐。
    """
    wh, loc, item = 1, 1, 99003
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)
    await seed_batch_slot(session, item=item, loc=loc, code="FK-CHK", qty=1, days=365)
    await session.commit()

    row = await session.execute(
        SA(
            """
           SELECT
             s.item_id,
             b.item_id       AS b_item,
             s.warehouse_id,
             b.warehouse_id  AS b_wh,
             s.batch_code,
             b.batch_code    AS b_code
             FROM stocks s
             JOIN batches b
               ON b.item_id      = s.item_id
              AND b.warehouse_id = s.warehouse_id
              AND b.batch_code   = s.batch_code
            WHERE s.item_id      = :i
              AND s.warehouse_id = :w
            LIMIT 1
        """
        ),
        {"i": item, "w": wh},
    )
    rec = row.first()
    assert rec is not None
    item_s, item_b, wh_s, wh_b, code_s, code_b = rec
    assert item_s == item_b
    assert wh_s == wh_b
    assert code_s == code_b
