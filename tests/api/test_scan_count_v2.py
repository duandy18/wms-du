# tests/api/test_scan_count_v2.py
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_scan_count_v2_adjusts_stock(client):
    """
    v2 /scan 盘点合同测试（API 层，不查 DB）：

    场景：
      1) 先通过 /scan(mode=receive) 收货 5 件某批次库存；
      2) 再通过 /scan(mode=count) 把该批次库存调整为 2；
      3) 验证 HTTP 返回 ok/committed 为 True。
    """

    warehouse_id = 1
    item_id = 3001
    batch_code = "BATCH-COUNT-V2"
    expiry_date = "2030-12-31"

    # 1) 先收货 5 件
    recv_payload = {
        "mode": "receive",
        "item_id": item_id,
        "qty": 5,
        "warehouse_id": warehouse_id,
        "batch_code": batch_code,
        "expiry_date": expiry_date,
        "ctx": {"device_id": "scan-count-v2-test"},
    }
    r1 = await client.post("/scan", json=recv_payload)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["ok"] is True, f"d1={d1}"
    assert d1["committed"] is True

    # 2) 再通过 count 把库存改为 2
    count_payload = {
        "mode": "count",
        "item_id": item_id,
        "qty": 2,
        "warehouse_id": warehouse_id,
        "batch_code": batch_code,
        "expiry_date": expiry_date,
        "ctx": {"device_id": "scan-count-v2-test"},
    }
    r2 = await client.post("/scan", json=count_payload)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["ok"] is True, f"d2={d2}"
    assert d2["committed"] is True
