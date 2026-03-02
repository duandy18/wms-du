import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_alembic_single_head_and_stocks_lot_contract(session: AsyncSession):
    """
    Alembic 迁移合约测试（Phase M-5 终态）

    目标：
    1. 确保 Alembic 是单头（alembic_version 只有一条）
    2. stocks_lot 必须存在且具备关键列/唯一约束（lot-world 主余额源）
    3. lots 表必须存在，且具备 canonical Lot 身份实体化的关键索引/约束。
       注意：Phase M-5 下 lots 不再承载时间事实（production/expiry）与历史字段。

    终态原则（重要）：
    - 不用“索引/约束名字”做合同（名字容易漂移）
    - 用“语义合同”做约束：唯一键/检查约束的真实定义必须满足终态规则
    """

    # 1) alembic_version 表应存在且仅一行（单 head）
    result = await session.execute(text("SELECT COUNT(*) FROM alembic_version"))
    assert int(result.scalar_one()) == 1

    # ------------------------------------------------------------------
    # 2) Phase M-5: stocks_lot DDL contract（主余额源）
    # ------------------------------------------------------------------

    # 2.1) stocks_lot 表必须存在
    stocks_lot_exists = await session.execute(
        text(
            """
            SELECT 1
              FROM information_schema.tables
             WHERE table_schema='public'
               AND table_name='stocks_lot'
             LIMIT 1
            """
        )
    )
    assert stocks_lot_exists.scalar_one_or_none() == 1, "stocks_lot table not found"

    # 2.2) stocks_lot 必备列集合（至少这些必须存在）
    cols_sl = await session.execute(
        text(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema='public'
               AND table_name='stocks_lot'
            """
        )
    )
    sl_cols = {r[0] for r in cols_sl.fetchall()}
    required_sl_cols = {
        "item_id",
        "warehouse_id",
        "lot_id",
        "qty",
    }
    missing_sl = required_sl_cols - sl_cols
    assert not missing_sl, f"stocks_lot missing columns: {sorted(missing_sl)}"

    # 2.3) stocks_lot 唯一约束必须存在：uq_stocks_lot_item_wh_lot
    cols_uq = await session.execute(
        text(
            """
            SELECT kcu.column_name
              FROM information_schema.table_constraints tc
              JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
               AND tc.table_schema = kcu.table_schema
               AND tc.table_name = kcu.table_name
             WHERE tc.table_schema='public'
               AND tc.table_name='stocks_lot'
               AND tc.constraint_type='UNIQUE'
               AND tc.constraint_name='uq_stocks_lot_item_wh_lot'
             ORDER BY kcu.ordinal_position
            """
        )
    )
    uq_cols = [r[0] for r in cols_uq.fetchall()]
    assert uq_cols, "uq_stocks_lot_item_wh_lot not found"
    assert set(uq_cols) >= {"item_id", "warehouse_id", "lot_id"}

    # ------------------------------------------------------------------
    # 3) Phase M-5: lots DDL contract（identity + policy snapshots）
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

    # 3.2) lots 必备列集合（终态：不要求 production/expiry 等时间事实列）
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
        # required policy snapshots
        "item_lot_source_policy_snapshot",
        "item_expiry_policy_snapshot",
        "item_derivation_allowed_snapshot",
        "item_uom_governance_enabled_snapshot",
        # optional shelf-life snapshots
        "item_shelf_life_value_snapshot",
        "item_shelf_life_unit_snapshot",
        "created_at",
    }
    missing = required_cols - lots_cols
    assert not missing, f"lots missing columns: {sorted(missing)}"

    # 3.3) 语义唯一性合同（不依赖 index name）：
    # - supplier lot：要求存在一个 UNIQUE 约束/索引，其 key 覆盖 (warehouse_id, item_id, lot_code)
    #   且限定 lot_code IS NOT NULL（partial unique 或等价约束）
    # - internal lot：要求存在一个 UNIQUE，覆盖 (warehouse_id, item_id, source_receipt_id, source_line_no)
    #   且限定 lot_code_source = 'INTERNAL'（partial unique 或等价约束）
    idx = await session.execute(
        text(
            """
            SELECT indexname, indexdef
              FROM pg_indexes
             WHERE schemaname='public'
               AND tablename='lots'
            """
        )
    )
    idx_rows = idx.fetchall()
    idx_defs = [str(r[1]) for r in idx_rows]

    def _has_supplier_unique(defs: list[str]) -> bool:
        for d in defs:
            ud = d.lower()
            if "unique" not in ud:
                continue
            if " on " not in ud:
                continue
            # columns
            if "(warehouse_id, item_id, lot_code)" in ud.replace('"', ""):
                # predicate
                if "where" in ud and "lot_code" in ud and "is not null" in ud:
                    return True
        return False

    def _has_internal_unique(defs: list[str]) -> bool:
        for d in defs:
            ud = d.lower().replace('"', "")
            if "unique" not in ud:
                continue
            if "(warehouse_id, item_id, source_receipt_id, source_line_no)" in ud:
                if "where" in ud and "lot_code_source" in ud and "internal" in ud:
                    return True
        return False

    assert _has_supplier_unique(idx_defs), "missing supplier-lot uniqueness: UNIQUE (warehouse_id,item_id,lot_code) WHERE lot_code IS NOT NULL"
    assert _has_internal_unique(idx_defs), "missing internal-lot uniqueness: UNIQUE (warehouse_id,item_id,source_receipt_id,source_line_no) WHERE lot_code_source='INTERNAL'"

    # 3.4) 关键 CHECK 约束（使用真实约束名）
    ck = await session.execute(
        text(
            """
            SELECT c.conname
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
             WHERE t.relname = 'lots'
               AND c.contype = 'c'
            """
        )
    )
    ck_names = {r[0] for r in ck.fetchall()}

    # 真实 schema（Phase M-5）中应至少包含以下两条：
    assert "ck_lots_lot_code_source" in ck_names, "missing ck_lots_lot_code_source"
    assert "ck_lots_internal_requires_source_receipt_line" in ck_names, "missing ck_lots_internal_requires_source_receipt_line"
