from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.snapshot_service import SnapshotService

pytestmark = pytest.mark.asyncio


async def test_query_inventory_snapshot_paged_structure(session: AsyncSession):
    """
    SnapshotService.query_inventory_snapshot_paged 应该返回：
      {
        "total": int,
        "offset": int,
        "limit": int,
        "rows": [ ... ]
      }
    且 rows 内元素结构与 /snapshot/inventory API 一致。
    """
    data = await SnapshotService.query_inventory_snapshot_paged(
        session,
        offset=0,
        limit=50,
    )

    assert isinstance(data, dict)
    assert set(["total", "offset", "limit", "rows"]).issubset(data.keys())

    rows = data["rows"]
    assert isinstance(rows, list)

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


async def test_query_inventory_snapshot_seed_items_present(session: AsyncSession):
    """
    复用 tests/api/test_snapshot_api.py 的思路：
    基线种子里这几个 item 应该出现在 snapshot 视图中：
      - 1 / 3001 / 3002 / 3003 / 4001
    """
    data = await SnapshotService.query_inventory_snapshot_paged(
        session,
        offset=0,
        limit=100,
    )
    rows = data["rows"]
    ids = {row["item_id"] for row in rows}

    for item_id in (1, 3001, 3002, 3003, 4001):
        assert item_id in ids


async def test_query_item_detail_for_seed_item(session: AsyncSession):
    """
    对一个已知有库存的 seed item（如 3001）做单品明细检查：
    - 返回结构完整
    - totals 与 slices 对得上（只做基本一致性检查）
    """
    item_id = 3001

    res = await SnapshotService.query_item_detail(
        session,
        item_id=item_id,
        pools=["MAIN"],
    )

    assert res["item_id"] == item_id
    assert "item_name" in res
    assert "totals" in res and "slices" in res

    totals = res["totals"]
    slices = res["slices"]

    assert isinstance(slices, list)
    assert isinstance(totals["on_hand_qty"], int)

    # 按当前实现，available = on_hand，reserved = 0
    assert totals["available_qty"] == totals["on_hand_qty"]
    assert totals["reserved_qty"] == 0

    if slices:
        s0 = slices[0]
        for k in (
            "warehouse_id",
            "warehouse_name",
            "pool",
            "batch_code",
            "on_hand_qty",
            "available_qty",
            "reserved_qty",
            "near_expiry",
            "is_top",
        ):
            assert k in s0
