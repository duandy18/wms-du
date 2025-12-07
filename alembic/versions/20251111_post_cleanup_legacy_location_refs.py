"""后清理：松绑 location 时代的约束/索引/外键，保留列作兼容字段

- stocks.location_id 改为可空，移除老时代唯一/索引
- 删除 stocks -> locations 的 FK（若仍在）
- 删除 stock_ledger -> locations / stocks 的 FK（若仍在），两列改为可空
- 去除 stock_ledger.warehouse_id 的默认 0（若存在）
"""

from alembic import op
import sqlalchemy as sa

revision = "20251111_post_cleanup_legacy_location_refs"
down_revision = "20251111_fix_stocks_wh_ledger_uc"
branch_labels = None
depends_on = None


def _constraint_exists(conn, table, name) -> bool:
    return bool(
        conn.execute(sa.text("""
            SELECT 1
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid=con.conrelid
            WHERE rel.relname=:t AND con.conname=:n
            LIMIT 1
        """), {"t": table, "n": name}).fetchone()
    )


def _index_exists(conn, name) -> bool:
    return bool(
        conn.execute(sa.text("SELECT 1 FROM pg_indexes WHERE indexname=:n LIMIT 1"),
                     {"n": name}).fetchone()
    )


def _col_exists(conn, table, column) -> bool:
    return bool(
        conn.execute(sa.text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_name=:t AND column_name=:c
            LIMIT 1
        """), {"t": table, "c": column}).fetchone()
    )


def upgrade():
    conn = op.get_bind()

    # 1) stocks：location 相关约束/索引卸载，location_id → 可空
    if _constraint_exists(conn, "stocks", "uq_stocks_nobatch"):
        op.drop_constraint("uq_stocks_nobatch", "stocks", type_="unique")

    if _index_exists(conn, "idx_stocks_loc"):
        op.drop_index("idx_stocks_loc", table_name="stocks")

    if _constraint_exists(conn, "stocks", "fk_stocks_location"):
        op.drop_constraint("fk_stocks_location", "stocks", type_="foreignkey")

    # 列改为可空（保留以兼容历史查询）
    if _col_exists(conn, "stocks", "location_id"):
        conn.execute(sa.text("ALTER TABLE stocks ALTER COLUMN location_id DROP NOT NULL"))

    # 2) stock_ledger：去除对 stocks/location 的 FK，列改为可空
    if _constraint_exists(conn, "stock_ledger", "fk_stock_ledger_stock_id"):
        op.drop_constraint("fk_stock_ledger_stock_id", "stock_ledger", type_="foreignkey")
    if _constraint_exists(conn, "stock_ledger", "fk_stock_ledger_location_id"):
        op.drop_constraint("fk_stock_ledger_location_id", "stock_ledger", type_="foreignkey")

    for col in ("stock_id", "location_id"):
        if _col_exists(conn, "stock_ledger", col):
            conn.execute(sa.text(f"ALTER TABLE stock_ledger ALTER COLUMN {col} DROP NOT NULL"))

    # 3) 去除 stock_ledger.warehouse_id 的默认 0（如果还有）
    try:
        conn.execute(sa.text("ALTER TABLE stock_ledger ALTER COLUMN warehouse_id DROP DEFAULT"))
    except Exception:
        pass  # 没有默认值则忽略


def downgrade():
    # 该清理迁移为“不可逆”友好降级：不恢复历史 FK / 唯一 / 索引 / 非空
    pass
