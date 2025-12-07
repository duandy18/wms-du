# tests/ci/test_db_invariants.py

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.grp_snapshot  # 分组标记，可按需调整


async def _seed_wh_item_stock(
    session: AsyncSession,
    *,
    wh_id: int,
    item_id: int,
    batch_code: str = "LEDGER-TEST-BATCH",
) -> int:
    """
    v2 口径下的最小种子数据：

    - 保证有一个 warehouses 行；
    - 保证有一个 items 行；
    - 保证有一个 batches 行（按 (item_id, warehouse_id, batch_code) 口径）；
    - 保证有一个 stocks 槽位 (item_id, warehouse_id, batch_code)；
    - 返回该 stocks.id，供后续 stock_ledger 使用。

    不再使用 location 维度。
    """

    # 1) 仓库（幂等）
    await session.execute(
        text(
            """
            INSERT INTO warehouses (id, name)
            VALUES (:wh_id, 'WH-LEDGER-TEST')
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"wh_id": wh_id},
    )

    # 2) 货品（幂等）
    await session.execute(
        text(
            """
            INSERT INTO items (id, sku, name)
            VALUES (:item_id, :sku, :name)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "item_id": item_id,
            "sku": f"SKU-{item_id}",
            "name": f"Item-{item_id}",
        },
    )

    # 3) 批次（按 v2 约定：item_id + warehouse_id + batch_code）
    #    测试环境每次用例前会 TRUNCATE，普通 INSERT 即可。
    await session.execute(
        text(
            """
            INSERT INTO batches (item_id, warehouse_id, batch_code)
            VALUES (:item_id, :wh_id, :batch_code)
            """
        ),
        {"item_id": item_id, "wh_id": wh_id, "batch_code": batch_code},
    )

    # 4) stocks 槽位：v2 唯一口径 (item_id, warehouse_id, batch_code)
    await session.execute(
        text(
            """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
            VALUES (:item_id, :wh_id, :batch_code, 0)
            """
        ),
        {"item_id": item_id, "wh_id": wh_id, "batch_code": batch_code},
    )

    row = await session.execute(
        text(
            """
            SELECT id
              FROM stocks
             WHERE item_id = :item_id
               AND warehouse_id = :wh_id
               AND batch_code = :batch_code
             LIMIT 1
            """
        ),
        {"item_id": item_id, "wh_id": wh_id, "batch_code": batch_code},
    )
    rec = row.first()
    assert rec, "stocks slot not created"
    stock_id = int(rec[0])

    await session.commit()
    return stock_id


@pytest.mark.asyncio
async def test_ledger_row_consistent_with_stock_slot(session: AsyncSession):
    """
    v2 行为验证（替代旧的“trigger 填 item_id/location_id”）：

    在 stock_ledger 上 INSERT 一条记录（显式写入 item_id / warehouse_id / batch_code），
    然后通过 stock_id 与 stocks 槽位 JOIN，验证两侧维度完全一致。

    目标不再是依赖 trigger 从 NULL 填值，而是验证：
      - 写 ledger 时必须与 stocks 槽位保持一致；
      - DB 层存在一条“ledger ↔ stocks”的一致性约束（至少在测试中被验证）。
    """
    wh_id, item_id = 1, 99901
    batch_code = "LEDGER-TEST-BATCH"

    # 1) 准备 stocks 槽位，并拿到 stock_id
    stock_id = await _seed_wh_item_stock(
        session,
        wh_id=wh_id,
        item_id=item_id,
        batch_code=batch_code,
    )

    # 2) 往 stock_ledger 插入一条记录，显式写入维度字段
    now = datetime.now(timezone.utc)
    ins = await session.execute(
        text(
            """
            INSERT INTO stock_ledger (
                stock_id,
                item_id,
                warehouse_id,
                batch_code,
                reason,
                ref,
                ref_line,
                delta,
                occurred_at,
                after_qty
            )
            VALUES (
                :sid,
                :item_id,
                :wh_id,
                :batch_code,
                'COUNT',
                'TRG-TEST',
                1,
                1,
                :ts,
                1
            )
            RETURNING id
            """
        ),
        {
            "sid": stock_id,
            "item_id": item_id,
            "wh_id": wh_id,
            "batch_code": batch_code,
            "ts": now,
        },
    )
    led_id = ins.scalar_one()
    await session.commit()

    # 3) 通过 JOIN stocks 校验 ledger 与 stocks 的维度一致性
    row2 = await session.execute(
        text(
            """
            SELECT
                l.stock_id,
                l.item_id,
                l.warehouse_id,
                l.batch_code,
                s.item_id,
                s.warehouse_id,
                s.batch_code
              FROM stock_ledger AS l
              JOIN stocks AS s
                ON s.id = l.stock_id
             WHERE l.id = :id
            """
        ),
        {"id": led_id},
    )
    r = row2.first()
    assert r, "ledger row not found via join to stocks"

    (
        got_stock_id,
        l_item_id,
        l_wh_id,
        l_batch_code,
        s_item_id,
        s_wh_id,
        s_batch_code,
    ) = r

    assert int(got_stock_id) == stock_id, "ledger.stock_id 异常"
    assert int(l_item_id) == int(s_item_id) == item_id, "ledger.item_id 与 stocks 不一致"
    assert int(l_wh_id) == int(s_wh_id) == wh_id, "ledger.warehouse_id 与 stocks 不一致"
    assert l_batch_code == s_batch_code == batch_code, "ledger.batch_code 与 stocks 不一致"
