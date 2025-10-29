# tests/services/test_inventory_adjust_fefo.py
from datetime import date, timedelta
import pytest

pytestmark = pytest.mark.asyncio

async def test_fefo_outbound_prefers_expired_then_near(session, stock_service, item_loc_fixture):
    item_id, location_id = item_loc_fixture  # (1,1) 起跑线 stocks=0
    today = date.today()

    # 先入两批：过期5、近效7 => stocks=12
    for code, exp, qty in [
        ("CC-EXPIRED", today - timedelta(days=1), 5),
        ("CC-NEAR",    today + timedelta(days=2), 7),
    ]:
        await stock_service.adjust(
            session=session, item_id=item_id, location_id=location_id,
            delta=qty, reason="INBOUND", ref="CC-IN",
            batch_code=code, production_date=None, expiry_date=exp, mode="NORMAL",
        )

    # FEFO 出库 -6，应该先扣掉过期批（5），再扣近效 1，stocks=6
    res = await stock_service.adjust(
        session=session, item_id=item_id, location_id=location_id,
        delta=-6, reason="OUTBOUND", ref="SO-001"
    )
    assert res["stock_after"] == 6
    assert res["ledger_id"] > 0
