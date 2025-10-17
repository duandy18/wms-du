import os
from contextlib import contextmanager

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


@contextmanager
def atomic_on():
    old = os.environ.get("OUTBOUND_ATOMIC")
    os.environ["OUTBOUND_ATOMIC"] = "true"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("OUTBOUND_ATOMIC", None)
        else:
            os.environ["OUTBOUND_ATOMIC"] = old


async def _seed_with_committed_session(
    async_session_maker, item_id: int, location_id: int, qty: int
):
    """
    使用独立会话写入并提交，避免测试事务不可见。
    """
    async with async_session_maker() as s:
        # items
        await s.execute(
            text(
                """
                INSERT INTO items(id, sku, name)
                VALUES (:iid, :sku, :name)
                ON CONFLICT (id) DO UPDATE SET sku=EXCLUDED.sku, name=EXCLUDED.name
                """
            ),
            {"iid": item_id, "sku": f"AT-{item_id}", "name": "原子模式-猫粮"},
        )
        # locations（必须带 warehouse_id）
        await s.execute(
            text(
                """
                INSERT INTO locations(id, warehouse_id, name)
                VALUES (:lid, 1, 'AT-L1')
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"lid": location_id},
        )
        # stocks：写入现势库存
        await s.execute(
            text(
                """
                INSERT INTO stocks(item_id, location_id, qty)
                VALUES (:iid, :lid, :qty)
                ON CONFLICT (item_id, location_id) DO UPDATE SET qty = EXCLUDED.qty
                """
            ),
            {"iid": item_id, "lid": location_id, "qty": qty},
        )
        await s.commit()


async def _get_qty(ac, item_id: int, location_id: int) -> int:
    r = await ac.get("/stock/query", params={"item_id": item_id, "location_id": location_id})
    assert r.status_code == 200, r.text
    rows = r.json().get("rows", [])
    return rows[0]["qty"] if rows else 0


async def test_outbound_atomic_rollback(ac, async_session_maker):
    """
    原子模式：任一行不足 -> 整单 409，且不扣减。
    用“独立会话提交”的方式造数，再通过 HTTP 调用 /outbound/commit 与 /stock/query 验证。
    """
    item_id, location_id = 301, 31

    # 先造 5 件（已提交）
    await _seed_with_committed_session(async_session_maker, item_id, location_id, 5)
    before = await _get_qty(ac, item_id, location_id)
    assert before == 5

    with atomic_on():
        r = await ac.post(
            "/outbound/commit",
            json={
                "ref": "SO-AT-1",
                "lines": [
                    {"item_id": item_id, "location_id": location_id, "qty": 3, "ref_line": "1"},
                    {"item_id": item_id, "location_id": location_id, "qty": 3, "ref_line": "2"},
                ],
            },
        )
        # 原子模式：任一行不足即 409，且不落账不扣减
        assert r.status_code == 409, r.text

    after = await _get_qty(ac, item_id, location_id)
    assert after == 5
