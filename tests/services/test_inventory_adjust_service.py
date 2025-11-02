import pytest
from datetime import date, timedelta

pytestmark = pytest.mark.asyncio

class _FakeCtx:
    def __init__(self, session):
        self.session = session

async def _stock_sum(session, item_id, warehouse_id):
    from sqlalchemy import text
    q = text("""
        SELECT COALESCE(SUM(qty), 0)
        FROM stocks
        WHERE item_id=:iid AND warehouse_id=:wid
    """)
    val = (await session.execute(q, {"iid": item_id, "wid": warehouse_id})).scalar()
    return int(val or 0)

async def _mk_batch(session, item_id=1, wh=1, loc=1, code="T-ADJ", exp=None):
    from sqlalchemy import text
    if exp is None:
        exp = date.today() + timedelta(days=30)
    await session.execute(text("""
        INSERT INTO batches(item_id, warehouse_id, location_id, batch_code, expire_at)
        VALUES (:i, :w, :l, :c, :e)
        ON CONFLICT DO NOTHING
    """), {"i": item_id, "w": wh, "l": loc, "c": code, "e": exp})
    await session.commit()
    return (item_id, wh, loc, code)

async def test_adjust_increase_then_decrease(session):
    from app.services.inventory_adjust import InventoryAdjustService

    item_id, wh, loc, code = await _mk_batch(session)
    svc = InventoryAdjustService()

    # +10
    await svc.adjust(session=session, item_id=item_id, warehouse_id=wh,
                     location_id=loc, batch_code=code, delta=10, reason="test+")
    assert await _stock_sum(session, item_id, wh) == 10

    # -3
    await svc.adjust(session=session, item_id=item_id, warehouse_id=wh,
                     location_id=loc, batch_code=code, delta=-3, reason="test-")
    assert await _stock_sum(session, item_id, wh) == 7

async def test_adjust_negative_guard(session):
    from app.services.inventory_adjust import InventoryAdjustService

    item_id, wh, loc, code = await _mk_batch(session)
    svc = InventoryAdjustService()

    await svc.adjust(session=session, item_id=item_id, warehouse_id=wh,
                     location_id=loc, batch_code=code, delta=5, reason="seed")
    # 试图 -10（超卖）
    with pytest.raises(Exception):
        await svc.adjust(session=session, item_id=item_id, warehouse_id=wh,
                         location_id=loc, batch_code=code, delta=-10, reason="over")
