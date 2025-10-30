import pytest

pytestmark = pytest.mark.grp_reverse

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


async def _seed_inbound(session, item_id, loc, qty):
    from app.services.stock_service import StockService

    svc = StockService()
    await svc.adjust(
        session=session, item_id=item_id, location_id=loc, delta=qty, reason="INBOUND", ref="SEED"
    )


async def test_reserve_and_release(session):
    from app.services.reservation_service import ReservationService

    engine = session.bind

    item, loc = 2001, 1
    await _seed_inbound(session, item, loc, 10)
    await session.commit()

    svc = ReservationService()

    # 预留 7
    await svc.reserve(session=session, ref="SO-RES-001", item_id=item, location_id=loc, qty=7)
    await session.commit()

    # 可用量：10-7=3
    av = await svc.available(session=session, item_id=item, location_id=loc)
    assert av["available"] == 3

    # 再次预留（幂等冲突不重复占用）
    await svc.reserve(session=session, ref="SO-RES-001", item_id=item, location_id=loc, qty=7)
    await session.commit()
    av2 = await svc.available(session=session, item_id=item, location_id=loc)
    assert av2["available"] == 3

    # 释放
    await svc.release(session=session, ref="SO-RES-001", item_id=item, location_id=loc)
    await session.commit()
    av3 = await svc.available(session=session, item_id=item, location_id=loc)
    assert av3["available"] == 10
