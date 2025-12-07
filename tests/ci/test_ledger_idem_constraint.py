import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_stock_ledger_idempotency_unique_exists(session):
    """
    合同：幂等键 (warehouse_id, batch_code, item_id, reason, ref, ref_line)
    必须存在唯一约束/唯一索引。

    说明：
      - 旧设计是 (reason, ref, ref_line, stock_id)，当前模型已统一到
        槽位维度 (item_id, warehouse_id, batch_code)；
      - 幂等性现在以“同一槽位 + 同一业务键 (reason, ref, ref_line)” 为单位，
        即 (warehouse_id, batch_code, item_id, reason, ref, ref_line) 唯一。
    """
    # PG: 读取唯一索引的列
    sql = text(
        """
        SELECT
          i.relname AS index_name,
          array_agg(a.attname ORDER BY a.attnum) AS cols
        FROM pg_class t
        JOIN pg_index ix ON t.oid = ix.indrelid
        JOIN pg_class i ON ix.indexrelid = i.oid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
        WHERE t.relname = 'stock_ledger' AND ix.indisunique
        GROUP BY i.relname
    """
    )
    try:
        rec = await session.execute(sql)
    except Exception:
        pytest.skip("stock_ledger not available; migration tests will cover DDL.")
        return

    uniq = rec.fetchall()
    cols_sets = {tuple(row[1]) for row in uniq}  # row[1] is array_agg

    # 目标列集合（顺序不敏感）
    target = ("warehouse_id", "batch_code", "item_id", "reason", "ref", "ref_line")

    assert any(
        set(cols) == set(target) for cols in cols_sets
    ), f"Missing idempotency unique on {target}. Found uniques: {sorted(cols_sets)}"
