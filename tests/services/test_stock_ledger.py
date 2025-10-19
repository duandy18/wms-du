# tests/services/test_stock_ledger.py
from datetime import date

from httpx import ASGITransport, AsyncClient
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_adjust_writes_ledger(session, stock_service, item_loc_fixture):
    item_id, location_id = item_loc_fixture

    res = await stock_service.adjust(
        session=session,
        item_id=item_id,
        location_id=location_id,
        delta=10,
        reason="INBOUND",
        ref="PO-001",
        batch_code="B20251006-A",
        production_date=date(2025, 9, 1),
        expiry_date=date(2026, 9, 1),
    )
    assert res["stock_after"] == 10
    assert res["batch_after"] == 10
    assert res["ledger_id"] > 0

    res2 = await stock_service.adjust(
        session=session,
        item_id=item_id,
        location_id=location_id,
        delta=-4,
        reason="OUTBOUND",
        ref="SO-001",
        batch_code="B20251006-A",
    )
    assert res2["stock_after"] == 6
    assert res2["batch_after"] == 6
    assert res2["ledger_id"] > 0

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/stock/ledger/query", json={"batch_code": "B20251006-A"})
        assert r.status_code == 200, r.text
        payload = r.json()
        assert payload["total"] >= 2
        deltas = [it["delta"] for it in payload["items"]]
        assert any(d == 10 for d in deltas) and any(d == -4 for d in deltas)
