# tests/services/test_scan_count.py
import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.grp_flow, pytest.mark.grp_scan]

from app.gateway.scan_count import scan_count_commit
from app.services.stock_service import StockService


async def _get_sum_qty(session, item_id: int, wh: int, loc: int) -> int:
    row = (
        await session.execute(
            text(
                """
        SELECT COALESCE(SUM(qty),0)::bigint
        FROM stocks
        WHERE item_id=:i AND warehouse_id=:w AND location_id=:l
        """
            ),
            {"i": item_id, "w": wh, "l": loc},
        )
    ).first()
    return int(row[0]) if row else 0


async def _seed_loc_by_service(session, loc_id: int, batch_code: str, qty: int) -> None:
    svc = StockService()
    await svc.adjust(
        session=session,
        item_id=1,
        location_id=loc_id,
        delta=qty,
        reason="INBOUND",
        ref=f"SEED:{batch_code}",
        batch_code=batch_code,
    )
    await session.commit()


@pytest.mark.asyncio
async def test_scan_count_probe(session, monkeypatch):
    # loc=1 造货 10
    await _seed_loc_by_service(session, 1, "B-COUNT", 10)

    monkeypatch.delenv("SCAN_REAL_COUNT", raising=False)

    before = await _get_sum_qty(session, 1, 1, 1)

    payload = {
        "device_id": "RF01",
        "operator": "tester",
        "barcode": "LOC:1",
        "mode": "count",
        "item_id": 1,
        "qty": 8,  # 盘点实数
        "ctx": {"warehouse_id": 1},
    }

    out = await scan_count_commit(session, payload)
    after = await _get_sum_qty(session, 1, 1, 1)

    assert out["result"]["status"] == "probe_ok"
    # 探活不落账
    assert after == before


@pytest.mark.asyncio
async def test_scan_count_real_commit(session, monkeypatch):
    # loc=1 造货 10
    await _seed_loc_by_service(session, 1, "B-COUNT", 10)

    monkeypatch.setenv("SCAN_REAL_COUNT", "1")

    before = await _get_sum_qty(session, 1, 1, 1)

    payload = {
        "device_id": "RF01",
        "operator": "tester",
        "barcode": "LOC:1",
        "mode": "count",
        "item_id": 1,
        "qty": 8,  # 盘点实数 → 差额 -2
        "ctx": {"warehouse_id": 1},
    }

    out = await scan_count_commit(session, payload)
    after = await _get_sum_qty(session, 1, 1, 1)

    assert out["result"]["status"] == "ok"
    assert (before - after) == 2  # 差额 -2
