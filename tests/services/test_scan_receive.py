# tests/services/test_scan_receive.py
import os
from datetime import date, timedelta

import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.grp_flow, pytest.mark.grp_scan]

from app.gateway.scan_receive import scan_receive_commit


async def _get_stock_qty(
    session, item_id: int, warehouse_id: int, location_id: int, batch_code: str
) -> int:
    sql = text(
        """
        SELECT COALESCE(qty,0)::bigint
        FROM stocks
        WHERE item_id=:item_id
          AND warehouse_id=:warehouse_id
          AND location_id=:location_id
          AND batch_code=:batch_code
        """
    )
    row = (
        await session.execute(
            sql,
            dict(
                item_id=item_id,
                warehouse_id=warehouse_id,
                location_id=location_id,
                batch_code=batch_code,
            ),
        )
    ).first()
    return int(row[0]) if row is not None else 0


@pytest.mark.asyncio
async def test_scan_receive_probe(session, monkeypatch):
    """
    保存点探活：执行成功但不落账（回滚）。
    使用基线存在的 item_id=1，避免 FK 报错。
    """
    monkeypatch.delenv("SCAN_REAL_RECEIVE", raising=False)
    monkeypatch.setenv("SCAN_STAGE_LOCATION_ID", "900")  # 不命中则回落到 900

    payload = {
        "device_id": "RF01",
        "operator": "tester",
        "barcode": "LOC:1",  # 基线夹具插入了 id=1 的库位
        "mode": "receive",
        "item_id": 1,  # 基线存在
        "qty": 5,
        "batch_code": "RCV-PROBE-1",
        "ctx": {"warehouse_id": 1},
    }

    before = await _get_stock_qty(session, 1, 1, 1, "RCV-PROBE-1")
    out = await scan_receive_commit(session, payload)
    after = await _get_stock_qty(session, 1, 1, 1, "RCV-PROBE-1")

    assert out["source"] == "scan_receive_commit"
    assert out["result"]["status"] == "probe_ok"
    # 探活不落账
    assert before == 0
    assert after == 0


@pytest.mark.asyncio
async def test_scan_receive_real_commit(session, monkeypatch):
    """
    真动作：入账生效。
    使用基线存在的 item_id=1 与库位 id=1。
    """
    monkeypatch.setenv("SCAN_REAL_RECEIVE", "1")
    monkeypatch.setenv("SCAN_STAGE_LOCATION_ID", "900")

    payload = {
        "device_id": "RF01",
        "operator": "tester",
        "barcode": "LOC:1",
        "mode": "receive",
        "item_id": 1,
        "qty": 7,
        "batch_code": "RCV-REAL-1",
        "expire_at": date.today() + timedelta(days=30),
        "ctx": {"warehouse_id": 1},
    }

    before = await _get_stock_qty(session, 1, 1, 1, "RCV-REAL-1")
    out = await scan_receive_commit(session, payload)
    after = await _get_stock_qty(session, 1, 1, 1, "RCV-REAL-1")

    assert out["source"] == "scan_receive_commit"
    assert out["result"]["status"] == "ok"
    assert out["result"]["received"] == 7
    assert after - before == 7

    # 可选三账体检（若过程/视图已装好可放开）
    # await session.execute(text("CALL snapshot_today();"))
    # tri = await session.execute(text("TABLE v_three_books;"))
    # assert tri is not None
