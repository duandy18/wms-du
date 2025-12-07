# tests/services/test_snapshot_service_dbproc.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, insert_snapshot

UTC = timezone.utc
pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_snapshot_dbproc_and_views(session: AsyncSession):
    wh, loc, item = 1, 1, 9301
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)

    d1 = date.today()
    d2 = d1 + timedelta(days=1)
    t1 = datetime.now(UTC).replace(microsecond=0)
    t2 = t1 + timedelta(days=1)

    await insert_snapshot(session, ts=t1, day=d1, item=item, loc=loc, on_hand=3, available=2)
    await insert_snapshot(session, ts=t2, day=d2, item=item, loc=loc, on_hand=7, available=5)
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
    got = [dict(r) for r in rows.mappings().all()]
    assert len(got) == 2
    assert int(got[0]["on_hand"]) == 3 and int(got[0]["available"]) == 2
    assert int(got[1]["on_hand"]) == 7 and int(got[1]["available"]) == 5
