import pytest

pytestmark = pytest.mark.grp_flow

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def seed_inbound(session, item, loc, qty):
    from app.services.stock_service import StockService

    await StockService().adjust(
        session=session, item_id=item, location_id=loc, delta=qty, reason="INBOUND", ref="OA-SEED"
    )


async def test_outbound_respects_available_not_onhand(session):
    from app.services.outbound_service import OutboundService

    item, loc = 82001, 1

    # on_hand=8
    await seed_inbound(session, item, loc, 8)
    # ACTIVE 预留 8 ⇒ available=0
    await session.execute(
        text(
            "INSERT INTO reservations(item_id,location_id,qty,ref,status) VALUES(:i,:l,8,'OA-RES','ACTIVE')"
        ),
        {"i": item, "l": loc},
    )
    await session.commit()

    res = await OutboundService.commit(
        session,
        platform="pdd",
        shop_id="",
        ref="OA-SO-1",
        warehouse_id=1,
        lines=[{"line_no": "1", "item_id": item, "location_id": loc, "qty": 1}],
    )
    # 应因 available=0 被拒绝
    assert any(r.get("status") == "INSUFFICIENT_STOCK" for r in res["results"])
