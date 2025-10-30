import pytest

pytestmark = pytest.mark.grp_reverse

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def seed_two_batches(session, item, loc):
    from datetime import date, timedelta

    from app.services.stock_service import StockService

    svc = StockService()
    today = date.today()
    await svc.adjust(
        session=session,
        item_id=item,
        location_id=loc,
        delta=5,
        reason="INBOUND",
        ref="RAV-B1",
        batch_code="B1",
        production_date=today,
        expiry_date=today + timedelta(days=5),
    )
    await svc.adjust(
        session=session,
        item_id=item,
        location_id=loc,
        delta=7,
        reason="INBOUND",
        ref="RAV-B2",
        batch_code="B2",
        production_date=today,
        expiry_date=today + timedelta(days=10),
    )


async def test_reservation_available_reads_view(session):
    from app.services.reservation_service import ReservationService

    item, loc = 83001, 1
    await seed_two_batches(session, item, loc)  # on_hand = 12
    await session.execute(
        text(
            "INSERT INTO reservations(item_id,location_id,qty,ref,status) VALUES(:i,:l,9,'RAV-RES','ACTIVE')"
        ),
        {"i": item, "l": loc},
    )
    await session.commit()

    svc = ReservationService()
    got = await svc.available(session=session, item_id=item, location_id=loc)
    assert got["on_hand"] == 12 and got["reserved"] == 9 and got["available"] == 3
