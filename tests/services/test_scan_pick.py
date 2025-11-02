# tests/services/test_scan_pick.py
import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.grp_flow, pytest.mark.grp_scan]

from app.gateway.scan_pick import scan_pick_commit
from app.services.stock_service import StockService


async def _get_qty(session, item_id: int, wh: int, loc: int, batch_code: str) -> int:
    row = (
        await session.execute(
            text(
                """
        SELECT COALESCE(qty,0)::bigint
        FROM stocks
        WHERE item_id=:i AND warehouse_id=:w AND location_id=:l AND batch_code=:b
        """
            ),
            {"i": item_id, "w": wh, "l": loc, "b": batch_code},
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
async def test_scan_pick_probe(session, monkeypatch):
    # 基线 loc=1 造货
    await _seed_loc_by_service(session, 1, "B-PICK", 10)

    monkeypatch.delenv("SCAN_REAL_PICK", raising=False)

    before = await _get_qty(session, 1, 1, 1, "B-PICK")

    payload = {
        "device_id": "RF01",
        "operator": "tester",
        "barcode": "LOC:1",  # 取货位
        "mode": "pick",
        "item_id": 1,
        "qty": 3,
        "ctx": {"warehouse_id": 1},
    }

    out = await scan_pick_commit(session, payload)
    after = await _get_qty(session, 1, 1, 1, "B-PICK")

    assert out["result"]["status"] in ("probe_ok", "ok")
    # 探活不落账
    assert after == before


@pytest.mark.asyncio
async def test_scan_pick_real_commit(session, monkeypatch):
    # 重新造货
    await _seed_loc_by_service(session, 1, "B-PICK", 10)

    monkeypatch.setenv("SCAN_REAL_PICK", "1")

    before = await _get_qty(session, 1, 1, 1, "B-PICK")

    payload = {
        "device_id": "RF01",
        "operator": "tester",
        "barcode": "LOC:1",
        "mode": "pick",
        "item_id": 1,
        "qty": 4,
        "ctx": {"warehouse_id": 1},
    }

    out = await scan_pick_commit(session, payload)
    after = await _get_qty(session, 1, 1, 1, "B-PICK")

    assert out["result"]["status"] == "ok"
    assert (before - after) == 4
