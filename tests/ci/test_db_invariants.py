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
    scope: str = "PROD",
) -> None:
    """
    v2 口径下的最小种子数据：

    - 保证有一个 warehouses 行；
    - 保证有一个 items 行；
    - 保证有一个 batches 行（按 (item_id, warehouse_id, batch_code) 口径）；
    - 保证有一个 stocks 槽位 (scope, warehouse_id, item_id, batch_code)。

    不再使用 location / stock_id 维度。
    """
    sc = (scope or "PROD").strip().upper()
    if sc not in ("PROD", "DRILL"):
        raise ValueError("scope must be PROD|DRILL")

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
    await session.execute(
        text(
            """
            INSERT INTO batches (item_id, warehouse_id, batch_code)
            VALUES (:item_id, :wh_id, :batch_code)
            ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
            """
        ),
        {"item_id": item_id, "wh_id": wh_id, "batch_code": batch_code},
    )

    # 4) stocks 槽位：scope + v2 唯一口径
    await session.execute(
        text(
            """
            INSERT INTO stocks (scope, warehouse_id, item_id, batch_code, qty)
            VALUES (:sc, :wh_id, :item_id, :batch_code, 0)
            ON CONFLICT ON CONSTRAINT uq_stocks_item_wh_batch DO NOTHING
            """
        ),
        {"sc": sc, "item_id": item_id, "wh_id": wh_id, "batch_code": batch_code},
    )

    await session.commit()


@pytest.mark.asyncio
async def test_ledger_row_consistent_with_stock_slot(session: AsyncSession):
    """
    v2 行为验证（无 stock_id 版）：

    - 先造一个 stocks 槽位 (scope, warehouse_id, item_id, batch_code, qty)
    - 再往 stock_ledger 写一条 COUNT 记录，写入相同的 scope/warehouse_id/item_id/batch_code
    - 然后通过 (scope, warehouse_id, item_id, batch_code) JOIN stocks，
      验证 ledger 维度与 stocks 槽位完全一致。
    """
    sc = "PROD"
    wh_id, item_id = 1, 99901
    batch_code = "LEDGER-TEST-BATCH"

    # 1) 准备 stocks 槽位
    await _seed_wh_item_stock(
        session,
        wh_id=wh_id,
        item_id=item_id,
        batch_code=batch_code,
        scope=sc,
    )

    # 2) 往 stock_ledger 插入一条记录，显式写入维度字段（含 scope）
    now = datetime.now(timezone.utc)
    row = await session.execute(
        text(
            """
            INSERT INTO stock_ledger (
                scope,
                warehouse_id,
                item_id,
                batch_code,
                reason,
                ref,
                ref_line,
                delta,
                occurred_at,
                after_qty
            )
            VALUES (
                :sc,
                :wh_id,
                :item_id,
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
            "sc": sc,
            "wh_id": wh_id,
            "item_id": item_id,
            "batch_code": batch_code,
            "ts": now,
        },
    )
    ledger_id = int(row.scalar_one())

    # 3) 通过 JOIN stocks 校验 ledger 与 stocks 的维度一致性（含 scope）
    row2 = await session.execute(
        text(
            """
            SELECT
              l.warehouse_id AS l_wh,
              l.item_id      AS l_item,
              l.batch_code   AS l_batch,
              s.warehouse_id AS s_wh,
              s.item_id      AS s_item,
              s.batch_code   AS s_batch
            FROM stock_ledger AS l
            JOIN stocks AS s
              ON s.scope        = l.scope
             AND s.warehouse_id = l.warehouse_id
             AND s.item_id      = l.item_id
             AND s.batch_code   = l.batch_code
           WHERE l.id = :lid
            """
        ),
        {"lid": ledger_id},
    )
    r = row2.mappings().first()
    assert r is not None, "ledger row not found via join to stocks"

    assert int(r["l_wh"]) == int(r["s_wh"]) == wh_id
    assert int(r["l_item"]) == int(r["s_item"]) == item_id
    assert r["l_batch"] == r["s_batch"] == batch_code
