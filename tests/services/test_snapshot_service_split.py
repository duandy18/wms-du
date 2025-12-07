# tests/services/test_snapshot_service_split.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, insert_snapshot

UTC = timezone.utc
pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_snapshot_upsert_grain(session: AsyncSession):
    wh, loc, item = 1, 1, 9401
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)

    d1 = date.today()
    d2 = d1 + timedelta(days=1)
    t1 = datetime.now(UTC).replace(microsecond=0)
    t1b = t1 + timedelta(seconds=30)
    t2 = t1 + timedelta(days=1)

    # day1 两条
    await insert_snapshot(session, ts=t1, day=d1, item=item, loc=loc, on_hand=2, available=1)
    await insert_snapshot(session, ts=t1b, day=d1, item=item, loc=loc, on_hand=4, available=3)
    # day2 一条
    await insert_snapshot(session, ts=t2, day=d2, item=item, loc=loc, on_hand=5, available=4)
    await session.commit()

    rows = await session.execute(
        text(
            """
        SELECT snapshot_date AS day,
               SUM(qty_on_hand)::bigint   AS on_hand,
               SUM(qty_available)::bigint AS available
          FROM stock_snapshots
         WHERE item_id=:i AND warehouse_id=:w
         GROUP BY day
         ORDER BY day ASC
    """
        ),
        {"i": item, "w": wh},
    )
    data = [dict(r) for r in rows.mappings().all()]
    assert len(data) == 2
    assert int(data[0]["on_hand"]) == 6 and int(data[0]["available"]) == 4
    assert int(data[1]["on_hand"]) == 5 and int(data[1]["available"]) == 4
