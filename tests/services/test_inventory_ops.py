import pytest

pytestmark = pytest.mark.grp_core

from datetime import date, timedelta

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _seed(session, item=3101, loc=1, code="IO-MOVE"):
    """重新建立固定基线库存 10。"""
    await session.begin()
    await session.execute(text("DELETE FROM stock_ledger WHERE item_id=:i"), {"i": item})
    for sql in [
        "DELETE FROM batches WHERE item_id=:i AND location_id=:l AND batch_code=:c",
        "DELETE FROM stocks  WHERE item_id=:i AND location_id=:l AND batch_code=:c",
    ]:
        await session.execute(text(sql), {"i": item, "l": loc, "c": code})
    await session.commit()

    from app.services.stock_service import StockService

    exp = date.today() + timedelta(days=30)
    await session.begin()
    await StockService().adjust(
        session=session,
        item_id=item,
        location_id=loc,
        batch_code=code,
        expiry_date=exp,
        delta=10,
        reason="INBOUND",
    )
    await session.commit()


async def _sum(session, item):
    r = await session.execute(
        text("SELECT COALESCE(SUM(qty),0) FROM stocks WHERE item_id=:i"), {"i": item}
    )
    return int(r.scalar() or 0)


async def test_transfer_basic(session):
    from app.services.inventory_ops import InventoryOpsService

    item, from_loc, to_loc = 3101, 1, 2
    await _seed(session, item=item, loc=from_loc)

    svc = InventoryOpsService()
    await session.begin()
    await svc.transfer(
        session=session,
        item_id=item,
        from_location_id=from_loc,
        to_location_id=to_loc,
        qty=6,
        reason="MOVE",
    )
    await session.commit()

    # 总量守恒
    assert await _sum(session, item) == 10

    a = await session.execute(
        text("SELECT qty FROM stocks WHERE item_id=:i AND location_id=:l"),
        {"i": item, "l": from_loc},
    )
    b = await session.execute(
        text("SELECT qty FROM stocks WHERE item_id=:i AND location_id=:l"),
        {"i": item, "l": to_loc},
    )
    assert int(a.scalar() or 0) == 4
    assert int(b.scalar() or 0) == 6


async def test_transfer_idempotent(session):
    from app.services.inventory_ops import InventoryOpsService

    item, from_loc, to_loc = 3102, 1, 3
    await _seed(session, item=item, loc=from_loc)

    svc = InventoryOpsService()
    ref = "MOVE-REF-1"

    await session.begin()
    await svc.transfer(
        session=session,
        item_id=item,
        from_location_id=from_loc,
        to_location_id=to_loc,
        qty=5,
        reason="MOVE",
        ref=ref,
    )
    await session.commit()

    await session.begin()
    await svc.transfer(
        session=session,
        item_id=item,
        from_location_id=from_loc,
        to_location_id=to_loc,
        qty=5,
        reason="MOVE",
        ref=ref,
    )
    await session.commit()

    a = await session.execute(
        text("SELECT SUM(delta) FROM stock_ledger WHERE reason='MOVE' AND ref=:r"),
        {"r": ref},
    )
    assert int(a.scalar() or 0) == 0
    c = await session.execute(
        text("SELECT COUNT(*) FROM stock_ledger WHERE reason='MOVE' AND ref=:r"),
        {"r": ref},
    )
    assert int(c.scalar() or 0) == 2
