# tests/api/test_stock_ledger.py
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_ledger_query_returns_adjust_history(session, stock_service, item_loc_fixture):
    item_id, location_id = item_loc_fixture

    r1 = await stock_service.adjust(
        session=session,
        item_id=item_id,
        location_id=location_id,
        delta=10,
        reason="INBOUND",
        ref="PO-LEDGER-1",
        batch_code="B20251006-A",
        production_date=date(2025, 9, 1),
        expiry_date=date(2026, 9, 1),
    )
    assert r1["stock_after"] == 10 and r1["batch_after"] == 10

    r2 = await stock_service.adjust(
        session=session,
        item_id=item_id,
        location_id=location_id,
        delta=-4,
        reason="OUTBOUND",
        ref="SO-LEDGER-1",
        batch_code="B20251006-A",
    )
    assert r2["stock_after"] == 6 and r2["batch_after"] == 6

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/stock/ledger/query", json={"batch_code": "B20251006-A"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] >= 2
        deltas = [it["delta"] for it in body["items"]]
        assert any(d == 10 for d in deltas) and any(d == -4 for d in deltas)
