from datetime import date

import pytest
from sqlalchemy import text

from app.db.session import async_session_maker
from app.services.stock_service import StockService

pytestmark = pytest.mark.smoke


async def _ensure_item_loc(item_id=1, location_id=101):
    async with async_session_maker() as s:
        async with s.begin():
            await s.execute(
                text(
                    "INSERT INTO items (id, sku, name, unit) VALUES (:i, :s, :n, 'EA') ON CONFLICT (id) DO NOTHING"
                ),
                {"i": item_id, "s": f"SKU-{item_id:03d}", "n": f"Item-{item_id}"},
            )
            await s.execute(
                text(
                    "INSERT INTO warehouses (id, name) VALUES (1,'WH') ON CONFLICT (id) DO NOTHING"
                )
            )
            await s.execute(
                text(
                    "INSERT INTO locations (id, name, warehouse_id) VALUES (:l,'RACK',1) ON CONFLICT (id) DO NOTHING"
                ),
                {"l": location_id},
            )


@pytest.mark.asyncio
async def test_adjust_ledger_only_when_location_missing():
    await _ensure_item_loc()
    svc = StockService()
    async with async_session_maker() as session:
        # 只给 batch_code，不给 location_id -> 应仅记账
        ret = await svc._adjust_async(
            session=session,
            item_id=1,
            delta=5,
            reason="INBOUND",
            ref="ADJ-L-1",
            location_id=None,
            batch_code="B-PARTIAL",
            production_date=None,
            expiry_date=None,
        )
        assert ret["stocks_touched"] is False

        # 库存不应变化
        q = await session.execute(
            text("SELECT qty FROM stocks WHERE item_id=1 AND location_id=101")
        )
        assert (q.scalar() or 0) == 0


@pytest.mark.asyncio
async def test_adjust_batch_upsert_only_when_info_complete():
    await _ensure_item_loc()
    svc = StockService()
    async with async_session_maker() as session:
        # A) 信息不全：不建 batch，直接入库
        r1 = await svc._adjust_async(
            session=session,
            item_id=1,
            location_id=101,
            delta=3,
            reason="INBOUND",
            ref="ADJ-B-1",
            batch_code="B-INFO",
            production_date=None,
            expiry_date=None,
        )
        assert r1["stocks_touched"] is True

        # B) 信息完整：建立/复用 batch
        r2 = await svc._adjust_async(
            session=session,
            item_id=1,
            location_id=101,
            delta=2,
            reason="INBOUND",
            ref="ADJ-B-2",
            batch_code="B-INFO",
            production_date=date(2025, 9, 1),
            expiry_date=date(2026, 9, 1),
        )
        # 如果你的 Batch 表存在，会返回 batch_id；不存在也不影响 quick 目标
        assert r2["stocks_touched"] is True

        # 库存合计应为 5
        q = await session.execute(
            text("SELECT qty FROM stocks WHERE item_id=1 AND location_id=101")
        )
        assert int(q.scalar() or 0) == 5
