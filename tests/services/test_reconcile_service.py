# tests/services/test_reconcile_service.py
from datetime import date, timedelta
import pytest

pytestmark = pytest.mark.asyncio

async def test_reconcile_up_and_down_stocks_baseline(session, stock_service, item_loc_fixture):
    item_id, location_id = item_loc_fixture
    today = date.today()

    # 入库：过期5 + 近效7 -> stocks=12
    for code, exp, qty in [
        ("CC-EXPIRED", today - timedelta(days=1), 5),
        ("CC-NEAR",    today + timedelta(days=2), 7),
    ]:
        await stock_service.adjust(
            session=session, item_id=item_id, location_id=location_id,
            delta=qty, reason="INBOUND", ref="CC-IN",
            batch_code=code, production_date=None, expiry_date=exp, mode="NORMAL"
        )

    # counted=15 -> diff=3 -> 入CC-ADJ
    res_up = await stock_service.reconcile_inventory(
        session=session, item_id=item_id, location_id=location_id,
        counted_qty=15, apply=True
    )
    assert res_up["diff"] == 3
    assert res_up["after_qty"] == 15
    assert res_up["applied"] is True
    assert res_up["moves"]  # 至少一条入库 move
