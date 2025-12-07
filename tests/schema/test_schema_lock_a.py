import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def test_stocks_schema_lock_a(session):
    """确保 stocks 表结构锁死在 (item_id, warehouse_id, location_id, batch_code) 唯一维度。"""
    # 必须存在这两个列
    for col in ("warehouse_id", "batch_code"):
        q = text(
            """
            SELECT 1 FROM information_schema.columns
             WHERE table_schema='public'
               AND table_name='stocks'
               AND column_name=:col
        """
        )
        r = await session.execute(q, {"col": col})
        assert r.scalar() == 1, f"stocks 缺少列: {col}"

    # 唯一约束必须存在
    q = text(
        """
        SELECT 1 FROM pg_constraint
         WHERE conname = 'uq_stocks_item_wh_loc_code'
           AND contype = 'u'
    """
    )
    r = await session.execute(q)
    assert r.scalar() == 1, "唯一约束 uq_stocks_item_wh_loc_code 不存在"

    # 外键必须存在
    q = text(
        """
        SELECT 1 FROM information_schema.table_constraints
         WHERE table_schema='public'
           AND table_name='stocks'
           AND constraint_name='fk_stocks_warehouse'
           AND constraint_type='FOREIGN KEY'
    """
    )
    r = await session.execute(q)
    assert r.scalar() == 1, "外键 fk_stocks_warehouse 不存在"


async def test_batches_schema_lock_a(session):
    """确保 batches.qty 非空且唯一索引存在。"""
    # qty 不可为 NULL
    q = text(
        """
        SELECT is_nullable
          FROM information_schema.columns
         WHERE table_schema='public'
           AND table_name='batches'
           AND column_name='qty'
    """
    )
    r = await session.execute(q)
    assert r.scalar() == "NO", "batches.qty 应为 NOT NULL"

    # 唯一索引存在
    q = text(
        """
        SELECT 1 FROM pg_class
         WHERE relname='uq_batches_item_wh_loc_code'
           AND relkind='i'
    """
    )
    r = await session.execute(q)
    assert r.scalar() == 1, "batches 缺少唯一索引 uq_batches_item_wh_loc_code"
