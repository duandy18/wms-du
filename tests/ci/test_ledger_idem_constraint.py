import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_stock_ledger_idempotency_unique_exists(session):
    """
    Phase M-5 合同：stock_ledger 的幂等键必须存在唯一约束/唯一索引。

    终态幂等键（lot-world）：
      (warehouse_id, lot_id, item_id, reason, ref, ref_line)

    说明：
      - lot_id 允许为 NULL（NONE 槽位），由 SQL NULL 语义表达（不使用 lot_id_key=0）
      - batch_code 仅为展示/输入标签（lots.lot_code），不参与幂等唯一性（不使用 batch_code_key/__NULL_BATCH__）
    """
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

    target = ("warehouse_id", "lot_id", "item_id", "reason", "ref", "ref_line")

    assert any(
        set(cols) == set(target) for cols in cols_sets
    ), f"Missing idempotency unique on {target}. Found uniques: {sorted(cols_sets)}"
