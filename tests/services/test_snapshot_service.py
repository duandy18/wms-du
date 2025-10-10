# tests/services/test_snapshot_service.py
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.snapshot_service import SnapshotService


@pytest.mark.asyncio
async def test_snapshot_run_for_date(session: AsyncSession):
    await session.execute(
        text(
            """
    INSERT INTO batches (id, batch_code, item_id, location_id, warehouse_id, production_date, expiry_date, qty)
    VALUES
      (32001, 'UT-A', 1, 1, 1, '2025-09-01', '2026-09-01', 10),
      (32002, 'UT-B', 1, 1, 1, '2025-09-10', '2026-09-10', 5);
    """
        )
    )
    await session.commit()

    d = date.today() - timedelta(days=1)
    n1 = await SnapshotService.run_for_date(session, d, sync_unbatched_from_stocks=False)
    # SQLAlchemy 2.0 需显式 text()（修复你报的 ArgumentError）
    await session.execute(text("UPDATE batches SET qty=12 WHERE id=32001;"))
    await session.commit()
    n2 = await SnapshotService.run_for_date(session, d, sync_unbatched_from_stocks=False)
    assert n2 == n1


@pytest.mark.asyncio
async def test_trends_api(client, session: AsyncSession):
    d0 = date.today() - timedelta(days=3)
    d1 = date.today() - timedelta(days=2)
    await SnapshotService.run_for_date(session, d0, sync_unbatched_from_stocks=False)
    await SnapshotService.run_for_date(session, d1, sync_unbatched_from_stocks=False)

    resp = client.get(f"/snapshot/trends?item_id=1&frm={d0}&to={d1}")
    assert resp.status_code == 200
    data = resp.json()
    assert all("snapshot_date" in x and "qty_on_hand" in x for x in data)
