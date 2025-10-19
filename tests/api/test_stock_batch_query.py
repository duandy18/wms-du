from datetime import date, timedelta

from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_stock_batch_query(client: AsyncClient, session):
    from app.services.stock_service import StockService

    svc = StockService()

    item_id = 101
    warehouse_id = 1
    location_id = 1

    today = date.today()
    for code, exp, qty in [
        ("B-EXP", today - timedelta(days=1), 10),
        ("B-SOON", today + timedelta(days=3), 20),
        ("B-FAR", today + timedelta(days=60), 30),
    ]:
        await svc.adjust(
            session=session,
            item_id=item_id,
            location_id=location_id,
            delta=qty,
            reason="INBOUND",
            ref="TEST-Q",
            batch_code=code,
            production_date=today - timedelta(days=30),
            expiry_date=exp,
            mode="NORMAL",
        )

    resp = await client.post(
        "/stock/batch/query", json={"item_id": item_id, "warehouse_id": warehouse_id}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 3
    codes = [row["batch_code"] for row in data["items"]]
    assert codes[:3] == ["B-EXP", "B-SOON", "B-FAR"]
    dtes = {row["batch_code"]: row["days_to_expiry"] for row in data["items"]}
    assert dtes["B-EXP"] < 0
    assert 0 <= dtes["B-SOON"] <= 10
