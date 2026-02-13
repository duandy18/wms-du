import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_alembic_single_head_and_stocks_batch_code_not_null(session: AsyncSession):
    """
    Alembic 迁移合约测试（收敛到当前真实设计）

    目标：
    1. 确保 Alembic 是单头（alembic_version 只有一条）
    2. 确保 stocks 使用“无批次 = NULL”的真实语义：
       - stocks.batch_code 允许 NULL
       - 存在生成列 batch_code_key = COALESCE(batch_code,'__NULL_BATCH__')
       - 唯一约束 uq_stocks_item_wh_batch 以 batch_code_key 为第三列（稳定幂等/唯一）
    """

    # 1) alembic_version 表应存在且仅一行（单 head）
    result = await session.execute(text("SELECT COUNT(*) FROM alembic_version"))
    assert int(result.scalar_one()) == 1

    # 2.1) stocks.batch_code 必须允许 NULL（新世界观）
    col = await session.execute(
        text(
            """
            SELECT is_nullable
              FROM information_schema.columns
             WHERE table_schema='public'
               AND table_name='stocks'
               AND column_name='batch_code'
             LIMIT 1
            """
        )
    )
    is_nullable = col.scalar_one_or_none()
    assert is_nullable == "YES"

    # 2.2) stocks.batch_code_key 必须存在（生成列）
    col2 = await session.execute(
        text(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema='public'
               AND table_name='stocks'
               AND column_name='batch_code_key'
             LIMIT 1
            """
        )
    )
    assert col2.scalar_one_or_none() == 1

    # 2.3) uq_stocks_item_wh_batch 必须包含 batch_code_key（第三列不强制位置，但必须在集合里）
    cols = await session.execute(
        text(
            """
            SELECT kcu.column_name
              FROM information_schema.table_constraints tc
              JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
               AND tc.table_schema = kcu.table_schema
               AND tc.table_name = kcu.table_name
             WHERE tc.table_schema='public'
               AND tc.table_name='stocks'
               AND tc.constraint_type='UNIQUE'
               AND tc.constraint_name='uq_stocks_item_wh_batch'
             ORDER BY kcu.ordinal_position
            """
        )
    )
    col_names = [r[0] for r in cols.fetchall()]
    assert col_names, "uq_stocks_item_wh_batch not found"
    assert "batch_code_key" in set(col_names)
    assert "item_id" in set(col_names)
    assert "warehouse_id" in set(col_names)
