import pytest

pytestmark = pytest.mark.grp_flow

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def seed_inbound(session, item, loc, qty):
    from app.services.stock_service import StockService

    await StockService().adjust(
        session=session, item_id=item, location_id=loc, delta=qty, reason="INBOUND", ref="IA-SEED"
    )


async def test_outbound_idem_audit(session):
    from app.services.outbound_service import OutboundService

    engine = session.bind
    item, loc = 85001, 1

    await seed_inbound(session, item, loc, 8)
    await session.commit()

    ref = "IA-001"
    # 第一次扣 8
    await OutboundService.commit(
        session,
        platform="pdd",
        shop_id="",
        ref=ref,
        warehouse_id=1,
        lines=[{"line_no": "1", "item_id": item, "location_id": loc, "qty": 8}],
    )
    await session.commit()
    # 第二次重放
    await OutboundService.commit(
        session,
        platform="pdd",
        shop_id="",
        ref=ref,
        warehouse_id=1,
        lines=[{"line_no": "1", "item_id": item, "location_id": loc, "qty": 8}],
    )
    await session.commit()

    row = await (await engine.begin()).execute(
        text(
            "SELECT outbound_rows, ledger_rows FROM v_outbound_idem_audit WHERE ref=:r AND item_id=:i AND location_id=:l"
        ),
        {"r": ref, "i": item, "l": loc},
    )
    m = row.first()
    assert m is not None and int(m[0]) == 1 and int(m[1]) >= 1
