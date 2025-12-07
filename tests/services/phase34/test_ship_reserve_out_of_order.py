# pytest: new file
# Path: tests/services/phase34/test_ship_reserve_out_of_order.py
import asyncio
from datetime import datetime

import pytest

pytestmark = pytest.mark.grp_phase34


async def _probe(async_client, path):
    try:
        r = await async_client.post(path, json={})
        return r.status_code in (200, 400, 401, 403, 404, 405, 422)
    except Exception:
        return False


async def _seed(async_session, qty):
    await async_session.execute(
        """
        DELETE FROM stocks WHERE item_id=3003 AND warehouse_id=1 AND location_id=900 AND batch_code='NEAR';
        INSERT INTO stocks (item_id, warehouse_id, location_id, batch_code, qty)
        VALUES (3003, 1, 900, 'NEAR', :qty);
    """,
        {"qty": qty},
    )
    await async_session.commit()


async def _read(async_session):
    r = await async_session.execute(
        """
        SELECT qty FROM stocks
        WHERE item_id=3003 AND warehouse_id=1 AND location_id=900 AND batch_code='NEAR'
    """
    )
    row = r.first()
    return 0 if not row else int(row[0])


@pytest.mark.asyncio
async def test_out_of_order_reserve_ship(async_client, async_session):
    has_ship = await _probe(async_client, "/outbound/ship/commit")
    has_resv = await _probe(async_client, "/reserve/plan")
    if not (has_ship and has_resv):
        pytest.skip("Endpoints /outbound/ship/commit or /reserve/plan missing; skip")

    await _seed(async_session, 10)

    # 场景 1：先 SHIP 5，后 RESERVE 5（迟到）
    ref_ship = "P34-OOO-SHIP-1"
    ref_resv = "P34-OOO-RESV-1"

    payload_ship = {
        "warehouse_id": 1,
        "lines": [
            {"item_id": 3003, "batch_code": "NEAR", "qty": 5, "ref": ref_ship, "ref_line": 1}
        ],
        "ts": datetime.utcnow().isoformat(),
    }
    payload_resv = {
        "warehouse_id": 1,
        "lines": [
            {"item_id": 3003, "batch_code": "NEAR", "qty": 5, "ref": ref_resv, "ref_line": 1}
        ],
        "ts": datetime.utcnow().isoformat(),
    }

    # 先出库
    r1 = await async_client.post("/outbound/ship/commit", json=payload_ship)
    assert r1.status_code in (200, 204, 409, 422)

    # 后到的 RESERVE 不应“再锁一次”或破坏一致性（通常应为 no-op 或记为补偿）
    r2 = await async_client.post("/reserve/plan", json=payload_resv)
    assert r2.status_code in (200, 204, 409, 422)

    qty_now = await _read(async_session)
    # 预期：实际库存应等于 10 - 5 = 5（迟到的 RESERVE 不改变实仓）
    assert qty_now == 5, f"expect qty=5 after ship-then-reserve-late, got {qty_now}"

    # 场景 2：先 RESERVE 7，后 SHIP 7（正常顺序）
    await _seed(async_session, 10)
    ref_resv2 = "P34-OOO-RESV-2"
    ref_ship2 = "P34-OOO-SHIP-2"
    payload_resv2 = {
        "warehouse_id": 1,
        "lines": [
            {"item_id": 3003, "batch_code": "NEAR", "qty": 7, "ref": ref_resv2, "ref_line": 1}
        ],
        "ts": datetime.utcnow().isoformat(),
    }
    payload_ship2 = {
        "warehouse_id": 1,
        "lines": [
            {"item_id": 3003, "batch_code": "NEAR", "qty": 7, "ref": ref_ship2, "ref_line": 1}
        ],
        "ts": datetime.utcnow().isoformat(),
    }

    r3 = await async_client.post("/reserve/plan", json=payload_resv2)
    assert r3.status_code in (200, 204, 409, 422)
    r4 = await async_client.post("/outbound/ship/commit", json=payload_ship2)
    assert r4.status_code in (200, 204, 409, 422)

    qty_now2 = await _read(async_session)
    assert qty_now2 == 3, f"expect qty=3 after reserve-then-ship, got {qty_now2}"
