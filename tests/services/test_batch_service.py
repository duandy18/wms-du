import pytest
from datetime import date, timedelta
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

async def _seed(session):
    from app.services.stock_service import StockService
    today = date.today()
    rows = [
        ("B-EXPIRED", today - timedelta(days=1), 3),
        ("B-NEAR",    today + timedelta(days=2), 4),
        ("B-LATE",    today + timedelta(days=30), 5),
    ]
    for code, exp, qty in rows:
        await StockService().adjust(session=session, item_id=3201, location_id=1,
                                    batch_code=code, expiry_date=exp, delta=qty, reason="seed")

async def test_pick_by_fefo_excludes_expired(session):
    from app.services.batch_service import BatchService
    await _seed(session)
    picked = await BatchService().pick_by_fefo(session=session, item_id=3201, location_id=1, qty=6)
    codes = [p["batch_code"] for p in picked]
    assert "B-EXPIRED" not in codes
    # 应优先用近效期
    assert codes[0] == "B-NEAR"
