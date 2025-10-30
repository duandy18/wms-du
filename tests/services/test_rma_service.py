import pytest

pytestmark = pytest.mark.grp_reverse

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _sum(engine, item, loc):
    async with engine.begin() as conn:
        row = await conn.execute(
            text(
                "SELECT COALESCE(qty,0) FROM stocks WHERE item_id=:iid AND location_id=:loc LIMIT 1"
            ),
            {"iid": item, "loc": loc},
        )
        return int(row.scalar() or 0)


async def _ensure_quarantine(engine, qloc=9001):
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
            INSERT INTO locations(id, name, warehouse_id, type)
            VALUES (:id, 'QUAR-1', 1, 'QUARANTINE')
            ON CONFLICT (id) DO NOTHING
        """
            ),
            {"id": qloc},
        )


async def _seed(session, item, loc, qty):
    from app.services.stock_service import StockService

    svc = StockService()
    await svc.adjust(
        session=session, item_id=item, location_id=loc, delta=qty, reason="INBOUND", ref="SEED"
    )


async def test_rma_return_good_and_defect(session):
    from app.services.rma_service import RMAService

    engine = session.bind
    item, loc, qloc = 2201, 1, 9001
    await _ensure_quarantine(engine, qloc)
    await _seed(session, item, loc, 10)
    await session.commit()

    svc = RMAService()

    # 良品回库 +3
    await svc.return_good(session=session, ref="RMA-001", item_id=item, location_id=loc, qty=3)
    await session.commit()
    assert await _sum(engine, item, loc) == 13

    # 次品 5 → 隔离位
    await svc.return_defect(
        session=session,
        ref="RMA-002",
        item_id=item,
        from_location_id=loc,
        quarantine_location_id=qloc,
        qty=5,
    )
    await session.commit()
    assert await _sum(engine, item, loc) == 8
    assert await _sum(engine, item, qloc) == 5
