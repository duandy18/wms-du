# tests/services/test_snapshot_service_split.py
from datetime import date, timedelta
import pytest
from sqlalchemy import text
from app.services.snapshot_service import SnapshotService

pytestmark = pytest.mark.asyncio

async def test_snapshot_upsert_grain(session):
    # 造两条 stocks，item=1 loc=1 → qty=8（模拟）
    await session.execute(text("""
    INSERT INTO stocks (item_id, location_id, qty) VALUES (1,1,8)
    ON CONFLICT (item_id, location_id) DO UPDATE SET qty=EXCLUDED.qty
    """))
    await session.commit()

    d = date.today() - timedelta(days=1)
    n = await SnapshotService.run_for_date(session, d, sync_unbatched_from_stocks=False)
    # 不严格断言 n；直接检查是否有该粒度的行写入
    row = await session.execute(text("""
      SELECT qty_on_hand, qty_available
      FROM stock_snapshots
      WHERE snapshot_date=:d AND warehouse_id=1 AND location_id=1 AND item_id=1
    """), {"d": d})
    qoh, qav = row.first()
    assert int(qoh) == 8 and int(qav) == 8

async def test_snapshot_trends_api(client, session):
    # 直接用 HTTP 客户端打 /snapshot/trends
    d0 = date.today() - timedelta(days=3)
    d1 = date.today() - timedelta(days=2)
    await SnapshotService.run_for_date(session, d0, sync_unbatched_from_stocks=False)
    await SnapshotService.run_for_date(session, d1, sync_unbatched_from_stocks=False)

    resp = client.get(f"/snapshot/trends?item_id=1&frm={d0}&to={d1}")
    assert resp.status_code == 200
    data = resp.json()
    assert all("snapshot_date" in x and "qty_on_hand" in x for x in data)
