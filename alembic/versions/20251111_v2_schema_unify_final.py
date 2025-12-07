"""v2 schema unify: stocks/ledger/batches/snapshots to warehouse+item+batch

Revision ID: 20251111_v2_schema_unify_final
Revises: 20251111_drop_legacy_nobatch_unique
Create Date: 2025-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = "20251111_v2_schema_unify_final"
down_revision = "20251111_drop_legacy_nobatch_unique"
branch_labels = None
depends_on = None


def _has_table(conn, table: str) -> bool:
    return sa.inspect(conn).has_table(table, schema="public")


def upgrade():
    conn = op.get_bind()

    # 1) warehouses.name 唯一索引（便于“查/插”）
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_warehouses_name ON warehouses(name);")

    # 2) stocks 统一为 v2
    # 2.1 qty → qty_on_hand（若仍是老列名）
    has_qty = conn.scalar(
        sa.text(
            """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='stocks' AND column_name='qty' LIMIT 1
    """
        )
    )
    if has_qty:
        op.execute("ALTER TABLE stocks RENAME COLUMN qty TO qty_on_hand;")

    # 2.2 确保 qty_on_hand 存在
    has_qoh = conn.scalar(
        sa.text(
            """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='stocks' AND column_name='qty_on_hand' LIMIT 1
    """
        )
    )
    if not has_qoh:
        op.add_column(
            "stocks",
            sa.Column("qty_on_hand", sa.Integer(), nullable=False, server_default="0"),
        )
        op.execute("ALTER TABLE stocks ALTER COLUMN qty_on_hand DROP DEFAULT")

    # 2.3 去除残留 location_id（如仍存在）
    has_loc = conn.scalar(
        sa.text(
            """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='stocks' AND column_name='location_id' LIMIT 1
    """
        )
    )
    if has_loc:
        op.execute("ALTER TABLE stocks DROP COLUMN IF EXISTS location_id")

    # 2.4 唯一键 (item_id, warehouse_id, batch_code)
    has_uc_stocks = conn.scalar(
        sa.text(
            """
        SELECT 1 FROM pg_constraint WHERE conname='uq_stocks_item_wh_batch'
    """
        )
    )
    if not has_uc_stocks:
        op.create_unique_constraint(
            "uq_stocks_item_wh_batch",
            "stocks",
            ["item_id", "warehouse_id", "batch_code"],
        )

    # 3) stock_ledger 幂等唯一： (warehouse_id, batch_code, item_id, reason, ref, ref_line)
    #    并移除 location_id 列（若存在）
    has_ledger_loc = conn.scalar(
        sa.text(
            """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='stock_ledger' AND column_name='location_id' LIMIT 1
    """
        )
    )
    if has_ledger_loc:
        op.execute("ALTER TABLE stock_ledger DROP COLUMN IF EXISTS location_id")

    has_uc_ledger = conn.scalar(
        sa.text(
            """
        SELECT 1 FROM pg_constraint WHERE conname='uq_ledger_idem_reason_refline_item_code_wh'
    """
        )
    )
    if not has_uc_ledger:
        op.create_unique_constraint(
            "uq_ledger_idem_reason_refline_item_code_wh",
            "stock_ledger",
            ["warehouse_id", "batch_code", "item_id", "reason", "ref", "ref_line"],
        )

    # 4) batches：退化为批次字典（不含 location_id），保留 warehouse 粒度或无仓版本二选一
    # 这里采用“无仓版本”，唯一 (item_id, batch_code)
    has_batches_loc = conn.scalar(
        sa.text(
            """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='batches' AND column_name='location_id' LIMIT 1
    """
        )
    )
    if has_batches_loc:
        op.execute("ALTER TABLE batches DROP COLUMN IF EXISTS location_id")

    # 若历史曾加过 warehouse_id，可按需要保留/移除；这里统一移除以简化为“共享批次字典”
    has_batches_wh = conn.scalar(
        sa.text(
            """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='batches' AND column_name='warehouse_id' LIMIT 1
    """
        )
    )
    if has_batches_wh:
        op.execute("ALTER TABLE batches DROP COLUMN IF EXISTS warehouse_id")

    has_uc_batches = conn.scalar(
        sa.text(
            """
        SELECT 1 FROM pg_constraint WHERE conname='uq_batches_item_code'
    """
        )
    )
    if not has_uc_batches:
        op.create_unique_constraint(
            "uq_batches_item_code",
            "batches",
            ["item_id", "batch_code"],
        )

    # 5) snapshots 唯一键： (snapshot_date, warehouse_id, item_id, batch_code)
    #    仅在表 snapshots 存在时才创建（干净库上可能完全没有 legacy snapshots 表）
    if _has_table(conn, "snapshots"):
        has_uc_snap = conn.scalar(
            sa.text(
                """
            SELECT 1 FROM pg_constraint WHERE conname='uq_snap_date_wh_item_code'
        """
            )
        )
        if not has_uc_snap:
            op.create_unique_constraint(
                "uq_snap_date_wh_item_code",
                "snapshots",
                ["snapshot_date", "warehouse_id", "item_id", "batch_code"],
            )


def downgrade():
    conn = op.get_bind()
    # 仅回退约束/索引（数据迁移不可逆）
    op.execute("DROP INDEX IF EXISTS uq_warehouses_name;")
    has_uc_snap = conn.scalar(
        sa.text("SELECT 1 FROM pg_constraint WHERE conname='uq_snap_date_wh_item_code'")
    )
    if has_uc_snap and sa.inspect(conn).has_table("snapshots", schema="public"):
        op.drop_constraint("uq_snap_date_wh_item_code", "snapshots", type_="unique")
    has_uc_batches = conn.scalar(
        sa.text("SELECT 1 FROM pg_constraint WHERE conname='uq_batches_item_code'")
    )
    if has_uc_batches:
        op.drop_constraint("uq_batches_item_code", "batches", type_="unique")
    has_uc_ledger = conn.scalar(
        sa.text("SELECT 1 FROM pg_constraint WHERE conname='uq_ledger_idem_reason_refline_item_code_wh'")
    )
    if has_uc_ledger:
        op.drop_constraint("uq_ledger_idem_reason_refline_item_code_wh", "stock_ledger", type_="unique")
    has_uc_stocks = conn.scalar(
        sa.text("SELECT 1 FROM pg_constraint WHERE conname='uq_stocks_item_wh_batch'")
    )
    if has_uc_stocks:
        op.drop_constraint("uq_stocks_item_wh_batch", "stocks", type_="unique")
