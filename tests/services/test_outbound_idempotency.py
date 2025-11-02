import pytest

pytestmark = pytest.mark.grp_flow

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _sum(engine, item_id, loc):
    async with engine.begin() as conn:
        row = await conn.execute(
            text(
                "SELECT COALESCE(qty,0) FROM stocks WHERE item_id=:iid AND location_id=:loc LIMIT 1"
            ),
            {"iid": item_id, "loc": loc},
        )
        return int(row.scalar() or 0)


async def _seed_two_batches(session, item_id, loc):
    from datetime import date, timedelta

    from app.services.stock_service import StockService

    svc = StockService()
    today = date.today()
    await svc.adjust(
        session=session,
        item_id=item_id,
        location_id=loc,
        delta=8,
        reason="INBOUND",
        ref="SEED1",
        batch_code="B1",
        production_date=today,
        expiry_date=today + timedelta(days=10),
    )
    await svc.adjust(
        session=session,
        item_id=item_id,
        location_id=loc,
        delta=8,
        reason="INBOUND",
        ref="SEED2",
        batch_code="B2",
        production_date=today,
        expiry_date=today + timedelta(days=20),
    )


async def test_outbound_idempotent_commit(session):
    from app.services.outbound_service import OutboundService

    engine = session.bind
    item, loc = 2101, 1
    await _seed_two_batches(session, item, loc)
    await session.commit()
    before = await _sum(engine, item, loc)
    assert before == 16

    ref = "SO-IDEM-001"
    # 第一次扣 8
    await OutboundService.commit(
        session,
        platform="pdd",
        shop_id="",
        ref=ref,
        warehouse_id=1,
        lines=[{"line_no": "X1", "item_id": item, "location_id": loc, "qty": 8}],
    )
    await session.commit()
    mid = await _sum(engine, item, loc)
    assert mid == 8

    # 第二次同 ref 重放（不应再扣）
    await OutboundService.commit(
        session,
        platform="pdd",
        shop_id="",
        ref=ref,
        warehouse_id=1,
        lines=[{"line_no": "X1", "item_id": item, "location_id": loc, "qty": 8}],
    )
    await session.commit()
    after = await _sum(engine, item, loc)
    assert after == 8
