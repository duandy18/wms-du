import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _seed_with_committed_session(async_session_maker):
    """
    使用独立会话写入并提交种子，避免测试事务不可见的问题。
    """
    async with async_session_maker() as s:
        # items
        await s.execute(
            text(
                """
                INSERT INTO items(id, sku, name)
                VALUES (201, 'AVL-201', '可用量测试-单点')
                ON CONFLICT (id) DO UPDATE SET sku=EXCLUDED.sku, name=EXCLUDED.name
                """
            )
        )
        # locations
        await s.execute(
            text(
                """
                INSERT INTO locations(id, warehouse_id, name)
                VALUES (21, 1, 'AVL-LOC')
                ON CONFLICT (id) DO NOTHING
                """
            )
        )
        # stocks: +10
        await s.execute(
            text(
                """
                INSERT INTO stocks(item_id, location_id, qty)
                VALUES (201, 21, 10)
                ON CONFLICT (item_id, location_id) DO UPDATE SET qty = EXCLUDED.qty
                """
            )
        )
        await s.commit()


async def test_stock_query_happy(ac, async_session_maker):
    """
    独立会话写入并提交 → HTTP 查询 /stock/query。
    """
    await _seed_with_committed_session(async_session_maker)

    # 精确过滤
    r = await ac.get("/stock/query", params={"item_id": 201, "location_id": 21})
    assert r.status_code == 200, r.text
    js = r.json()
    assert "rows" in js and len(js["rows"]) >= 1
    row = js["rows"][0]
    assert row["qty"] == 10
    assert row["available"] == 10

    # q 模糊搜索（命中 name/sku；若你的数据不含中文名，也至少应返回结构化结果）
    r2 = await ac.get("/stock/query", params={"q": "可用量"})
    assert r2.status_code == 200, r2.text
    assert "rows" in r2.json()
