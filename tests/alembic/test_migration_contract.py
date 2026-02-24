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
    3. Phase 2 Step 1 合同：lots 表必须存在，且具备 canonical 批次实体化的关键约束/索引。
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

    # ------------------------------------------------------------------
    # 3) Phase 2 Step 1: lots DDL contract
    # ------------------------------------------------------------------

    # 3.1) lots 表必须存在
    lots_exists = await session.execute(
        text(
            """
            SELECT 1
              FROM information_schema.tables
             WHERE table_schema='public'
               AND table_name='lots'
             LIMIT 1
            """
        )
    )
    assert lots_exists.scalar_one_or_none() == 1, "lots table not found"

    # 3.2) lots 必备列集合（至少这些必须存在）
    cols3 = await session.execute(
        text(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema='public'
               AND table_name='lots'
            """
        )
    )
    lots_cols = {r[0] for r in cols3.fetchall()}
    required_cols = {
        "id",
        "warehouse_id",
        "item_id",
        "lot_code_source",
        "lot_code",
        "source_receipt_id",
        "source_line_no",
        "production_date",
        "expiry_date",
        "expiry_source",
        "shelf_life_days_applied",
        "created_at",
    }
    missing = required_cols - lots_cols
    assert not missing, f"lots missing columns: {sorted(missing)}"

    # 3.3) partial unique indexes 必须存在 + predicate 必须正确
    idx = await session.execute(
        text(
            """
            SELECT indexname, indexdef
              FROM pg_indexes
             WHERE schemaname='public'
               AND tablename='lots'
               AND indexname IN (
                 'uq_lots_supplier_wh_item_lot_code',
                 'uq_lots_internal_wh_item_source'
               )
             ORDER BY indexname
            """
        )
    )
    idx_rows = idx.fetchall()
    idx_map = {r[0]: r[1] for r in idx_rows}

    assert "uq_lots_supplier_wh_item_lot_code" in idx_map, "missing uq_lots_supplier_wh_item_lot_code"
    assert "uq_lots_internal_wh_item_source" in idx_map, "missing uq_lots_internal_wh_item_source"

    # predicate（WHERE）必须包含 lot_code_source 过滤
    sup_def = idx_map["uq_lots_supplier_wh_item_lot_code"]
    int_def = idx_map["uq_lots_internal_wh_item_source"]

    assert "WHERE" in sup_def and "lot_code_source" in sup_def and "SUPPLIER" in sup_def, sup_def
    assert "WHERE" in int_def and "lot_code_source" in int_def and "INTERNAL" in int_def, int_def

    # 3.4) 关键 CHECK 约束至少要存在（lot_code_source 枚举）
    ck = await session.execute(
        text(
            """
            SELECT c.conname
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
             WHERE t.relname = 'lots'
               AND c.contype = 'c'
               AND c.conname IN (
                 'ck_lots_lot_code_source',
                 'ck_lots_supplier_requires_lot_code_and_no_source',
                 'ck_lots_internal_requires_source'
               )
            """
        )
    )
    ck_names = {r[0] for r in ck.fetchall()}

    assert "ck_lots_lot_code_source" in ck_names, "missing ck_lots_lot_code_source"
    assert (
        "ck_lots_supplier_requires_lot_code_and_no_source" in ck_names
    ), "missing ck_lots_supplier_requires_lot_code_and_no_source"
    assert "ck_lots_internal_requires_source" in ck_names, "missing ck_lots_internal_requires_source"
