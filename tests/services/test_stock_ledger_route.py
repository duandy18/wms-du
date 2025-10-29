# tests/services/test_stock_ledger_route.py
from datetime import date
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

pytestmark = pytest.mark.asyncio

async def test_ledger_query_by_batch_code(session, stock_service, item_loc_fixture):
    item_id, location_id = item_loc_fixture

    # +10 再 -4
    await stock_service.adjust(
        session=session, item_id=item_id, location_id=location_id,
        delta=10, reason="INBOUND", ref="PO-001",
        batch_code="B-LEDGER-A", production_date=date(2025, 9, 1), expiry_date=date(2026, 9, 1)
    )
    await stock_service.adjust(
        session=session, item_id=item_id, location_id=location_id,
        delta=-4, reason="OUTBOUND", ref="SO-001", batch_code="B-LEDGER-A"
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/stock/ledger/query", json={"batch_code":"B-LEDGER-A"})
        assert r.status_code == 200, r.text
        payload = r.json()
        deltas = [it["delta"] for it in payload["items"]]
        assert any(d == 10 for d in deltas) and any(d == -4 for d in deltas)
