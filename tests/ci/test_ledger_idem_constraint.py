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
      - lot_id 是必填结构锚点；不允许 lot_id_key=0 / sentinel。
      - batch_code 仅为展示/输入标签（lots.lot_code），不参与幂等唯一性。
      - stock_ledger 不允许回潮 batch_code / batch_code_key / lot_id_key。
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

    columns_rec = await session.execute(
        text(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema='public'
               AND table_name='stock_ledger'
            """
        )
    )
    columns = {str(row[0]) for row in columns_rec.fetchall()}

    forbidden = {"batch_code", "batch_code_key", "lot_id_key"} & columns
    assert not forbidden, f"stock_ledger must not contain retired batch-world columns: {sorted(forbidden)}"

    nullable_rec = await session.execute(
        text(
            """
            SELECT is_nullable
              FROM information_schema.columns
             WHERE table_schema='public'
               AND table_name='stock_ledger'
               AND column_name='lot_id'
            """
        )
    )
    is_nullable = (nullable_rec.scalar_one_or_none() or "").strip().upper()
    assert is_nullable == "NO", "stock_ledger.lot_id must be NOT NULL in lot-world"
