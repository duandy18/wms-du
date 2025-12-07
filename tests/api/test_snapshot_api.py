# tests/api/test_snapshot_api.py
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

try:
    import httpx

    from app.main import app
except Exception:
    httpx = None
    app = None


@pytest.mark.asyncio
async def test_snapshot_inventory_basic(client: "httpx.AsyncClient"):
    """
    /snapshot/inventory 应该返回分页结果：
      {
        "total": int,
        "offset": int,
        "limit": int,
        "rows": [ ... ]
      }
    且 rows 中的元素包含 item_id / item_name / total_qty / top2_locations。
    """
    if httpx is None or app is None:
        pytest.skip("httpx or app unavailable")

    resp = await client.get("/snapshot/inventory")
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, dict)
    assert "total" in data and "offset" in data and "limit" in data and "rows" in data

    rows = data["rows"]
    assert isinstance(rows, list)

    # 基线数据来自 tests/conftest.py 的种子：
    # - item_id 1, 3001, 3002, 3003, 4001
    # 这里不对具体值做硬编码，只检查结构和基本合理性。
    if rows:
        row0 = rows[0]
        for key in ("item_id", "item_name", "total_qty", "top2_locations"):
            assert key in row0

        assert isinstance(row0["item_id"], int)
        assert isinstance(row0["item_name"], str)
        assert isinstance(row0["total_qty"], int)
        assert row0["total_qty"] >= 0

        top2 = row0["top2_locations"]
        assert isinstance(top2, list)
        if top2:
            loc0 = top2[0]
            for lk in ("warehouse_id", "batch_code", "qty"):
                assert lk in loc0


@pytest.mark.asyncio
async def test_snapshot_inventory_seed_items_present(client: "httpx.AsyncClient"):
    """
    对基线种子里的几个关键 item 做一个存在性校验：
      - 1 / 3001 / 3002 / 3003 / 4001
    """
    if httpx is None or app is None:
        pytest.skip("httpx or app unavailable")

    resp = await client.get("/snapshot/inventory")
    assert resp.status_code == 200
    data = resp.json()
    rows = data["rows"]
    ids = {row["item_id"] for row in rows}

    # 基线插入的五个 item 都应当能在 snapshot/inventory 里被看到
    for item_id in (1, 3001, 3002, 3003, 4001):
        assert item_id in ids
