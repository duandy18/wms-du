# tests/api/test_scan_pick_v2.py
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_scan_pick_v2_decreases_stock(client):
    """
    v2 /scan 拣货合同测试（API 层，不查 DB）：

    场景：
      1) 先通过 /scan(mode=receive) 收货 10 件某批次库存；
      2) 再通过 /scan(mode=pick) 拣货 4 件；
      3) 验证 HTTP 返回 ok/committed 为 True。

    底层库存变动细节由 services 层测试覆盖（StockService/handle_pick）。
    """

    warehouse_id = 1
    item_id = 3001
    batch_code = "BATCH-PICK-V2"
    expiry_date = "2030-12-31"

    # 1) 先收货 10 件
    recv_payload = {
        "mode": "receive",
        "item_id": item_id,
        "qty": 10,
        "warehouse_id": warehouse_id,
        "batch_code": batch_code,
        "expiry_date": expiry_date,
        "ctx": {"device_id": "scan-pick-v2-test"},
    }
    r1 = await client.post("/scan", json=recv_payload)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["ok"] is True, f"d1={d1}"
    assert d1["committed"] is True

    # 2) 通过 pick 拣货 4 件
    pick_payload = {
        "mode": "pick",
        "item_id": item_id,
        "qty": 4,
        "warehouse_id": warehouse_id,
        "batch_code": batch_code,
        "ctx": {"device_id": "scan-pick-v2-test"},
    }
    r2 = await client.post("/scan", json=pick_payload)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["ok"] is True, f"d2={d2}"
    assert d2["committed"] is True
