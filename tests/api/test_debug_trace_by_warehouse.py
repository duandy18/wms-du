# tests/api/test_debug_trace_by_warehouse.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item

from app.services.stock.lots import ensure_lot_full
from app.services.stock_service import StockService

pytestmark = pytest.mark.asyncio
UTC = timezone.utc


async def test_debug_trace_filter_by_warehouse(client, session: AsyncSession):
    """
    验证 /debug/trace/{trace_id}?warehouse_id=... 过滤逻辑：

    - 同一个 trace_id 下，在 WH1 和 WH2 各写一条 ledger 负账；
    - 不带 warehouse_id 时，trace 中应出现两个仓的 ledger 事件；
    - 带 warehouse_id=1 时，只应看到 WH1 的 ledger 事件。
    """
    trace_id = "TRACE-WH-FILTER-1"
    item_id = 9001
    wh1, wh2 = 1, 2
    batch1, batch2 = "B-WH1", "B-WH2"

    # 准备两个仓的库存槽位
    await ensure_wh_loc_item(session, wh=wh1, loc=wh1, item=item_id)
    await ensure_wh_loc_item(session, wh=wh2, loc=wh2, item=item_id)

    # 终态合同：本测试要用 batch_code，所以必须把该 item 设为 REQUIRED
    await session.execute(
        text("UPDATE items SET expiry_policy='REQUIRED'::expiry_policy WHERE id=:i"),
        {"i": int(item_id)},
    )
    await session.commit()

    stock_svc = StockService()
    now = datetime.now(UTC)

    # ✅ 显式种 WH1 批次槽位库存
    lot1 = await ensure_lot_full(
        session,
        item_id=int(item_id),
        warehouse_id=int(wh1),
        lot_code=str(batch1),
        production_date=None,
        expiry_date=None,
    )
    await stock_svc.adjust_lot(
        session=session,
        item_id=int(item_id),
        warehouse_id=int(wh1),
        lot_id=int(lot1),
        delta=10,
        reason="TEST_SEED",
        ref="SEED-WH1",
        ref_line=1,
        occurred_at=now,
        batch_code=str(batch1),
        production_date=None,
        expiry_date=None,
        trace_id=trace_id,
    )

    # ✅ 显式种 WH2 批次槽位库存
    lot2 = await ensure_lot_full(
        session,
        item_id=int(item_id),
        warehouse_id=int(wh2),
        lot_code=str(batch2),
        production_date=None,
        expiry_date=None,
    )
    await stock_svc.adjust_lot(
        session=session,
        item_id=int(item_id),
        warehouse_id=int(wh2),
        lot_id=int(lot2),
        delta=10,
        reason="TEST_SEED",
        ref="SEED-WH2",
        ref_line=1,
        occurred_at=now,
        batch_code=str(batch2),
        production_date=None,
        expiry_date=None,
        trace_id=trace_id,
    )

    # 在 WH1 写一条 ledger 负账
    await stock_svc.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=wh1,
        delta=-2,
        reason="UNIT_TEST_WH1",
        ref="REF-WH1",
        ref_line=1,
        occurred_at=now,
        batch_code=batch1,
        trace_id=trace_id,
    )

    # 在 WH2 写一条 ledger 负账
    await stock_svc.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=wh2,
        delta=-3,
        reason="UNIT_TEST_WH2",
        ref="REF-WH2",
        ref_line=1,
        occurred_at=now + timedelta(seconds=1),
        batch_code=batch2,
        trace_id=trace_id,
    )

    await session.commit()

    # 1) 不带 warehouse_id，应该看到两个仓的 ledger 事件
    resp_all = await client.get(f"/debug/trace/{trace_id}")
    assert resp_all.status_code == 200, resp_all.text
    data_all = resp_all.json()
    events_all = data_all["events"]
    ledger_all = [e for e in events_all if e["source"] == "ledger"]
    wh_set = {e["raw"].get("warehouse_id") for e in ledger_all}
    assert wh1 in wh_set and wh2 in wh_set

    # 2) 带 warehouse_id=1 时，只看到 WH1 的 ledger 事件
    resp_w1 = await client.get(f"/debug/trace/{trace_id}?warehouse_id={wh1}")
    assert resp_w1.status_code == 200, resp_w1.text
    data_w1 = resp_w1.json()
    assert data_w1["warehouse_id"] == wh1

    events_w1 = data_w1["events"]
    ledger_w1 = [e for e in events_w1 if e["source"] == "ledger"]
    assert ledger_w1, "expected at least one ledger event for WH1"

    for e in ledger_w1:
        assert e["raw"].get("warehouse_id") == wh1
