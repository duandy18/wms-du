import pytest

pytestmark = pytest.mark.grp_core

# tests/services/test_inventory_adjust_inbound.py
from datetime import date

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def test_inbound_normal_increases_stocks_and_batch(session, stock_service, item_loc_fixture):
    item_id, location_id = item_loc_fixture  # (1,1) 起跑线 stocks=0

    res = await stock_service.adjust(
        session=session,
        item_id=item_id,
        location_id=location_id,
        delta=10,
        reason="INBOUND",
        ref="PO-001",
        batch_code="B-NORMAL-01",
        production_date=date(2025, 9, 1),
        expiry_date=date(2026, 9, 1),
        mode="NORMAL",
    )
    assert res["stock_after"] == 10
    assert res["batch_after"] == 10
    assert res["ledger_id"] > 0

    # 账面=权威，批次一致
    q = await session.execute(
        text("SELECT qty FROM stocks WHERE item_id=:i AND location_id=:l"),
        {"i": item_id, "l": location_id},
    )
    assert int(q.scalar_one()) == 10
