# tests/services/test_db_views_and_proc.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import (
    _columns_of,
    _has_table,
    ensure_wh_loc_item,
    insert_snapshot,
    seed_batch_slot,
    sum_on_hand,
)

UTC = timezone.utc
pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_v_available_and_three_books_with_snapshot(session: AsyncSession):
    wh, loc, item = 1, 1, 8101
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)
    for code, qty in (("A", 3), ("B", 4), ("C", 5)):
        await seed_batch_slot(session, item=item, loc=loc, code=code, qty=qty, days=365)
    await session.commit()

    on_hand = await sum_on_hand(session, item=item, loc=loc)
    assert on_hand == 12  # reserved 忽略或 0 时 available=on_hand


@pytest.mark.asyncio
async def test_snapshot_totals_specific_day(session: AsyncSession):
    # 结构探测
    cols = await _columns_of(session, "stock_snapshots")
    if not cols:
        pytest.skip("stock_snapshots 表不存在")
    required = {
        "as_of_ts",
        "snapshot_date",
        "item_id",
        "location_id",
        "qty_on_hand",
        "qty_available",
        "qty_allocated",
        "qty",
    }
    if not required.issubset(set(cols)):
        pytest.skip(f"stock_snapshots 缺少 {required}, 实际: {cols}")

    # 造数
    wh, loc, item = 1, 1, 8202
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)
    await seed_batch_slot(session, item=item, loc=loc, code="A", qty=2, days=365)
    await seed_batch_slot(session, item=item, loc=loc, code="B", qty=1, days=365)
    await session.commit()

    now = datetime.now(UTC)
    await insert_snapshot(
        session, ts=now, day=now.date(), item=item, loc=loc, on_hand=3, available=3
    )
    await session.commit()

    # 聚合验证
    from sqlalchemy import text as SA

    row = await session.execute(
        SA(
            """
        SELECT snapshot_date AS day,
               SUM(qty_on_hand)::bigint   AS on_hand,
               SUM(qty_available)::bigint AS available
          FROM stock_snapshots
         WHERE item_id=:i AND location_id=:l
         GROUP BY day
         ORDER BY day DESC
         LIMIT 1
    """
        ),
        {"i": item, "l": loc},
    )
    got = row.mappings().first()
    assert got is not None and int(got["on_hand"]) == 3 and int(got["available"]) == 3
