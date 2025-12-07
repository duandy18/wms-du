"""v2 core: drop stock_ledger.location_id; create snapshots (warehouse+item+batch)

Revision ID: 20251111_v2_core_drop_ledger_loc_and_create_snapshots
Revises: 20251111_fix_bacthes_fk_and_ledger_ref_nn
Create Date: 2025-11-11
"""
from alembic import op
import sqlalchemy as sa


# --- revision identifiers ---
revision = "20251111_v2_core_drop_ledger_loc_and_create_snapshots"
down_revision = "20251111_fix_bacthes_fk_and_ledger_ref_nn"  # ← 按你当前 head 填
branch_labels = None
depends_on = None


def _col_exists(conn, table: str, column: str, schema: str = "public") -> bool:
    insp = sa.inspect(conn)
    return any(c["name"] == column for c in insp.get_columns(table, schema=schema))


def _table_exists(conn, table: str, schema: str = "public") -> bool:
    insp = sa.inspect(conn)
    return table in insp.get_table_names(schema=schema)


def _uc_exists(conn, table: str, uc_name: str, schema: str = "public") -> bool:
    res = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM   pg_constraint c
            WHERE  c.conname = :name
            AND    c.conrelid = (:schema || '.' || :table)::regclass
            """
        ),
        {"name": uc_name, "schema": schema, "table": table},
    ).scalar()
    return bool(res)


def upgrade():
    conn = op.get_bind()

    # 1) stock_ledger: drop location_id if exists (幂等)
    if _col_exists(conn, "stock_ledger", "location_id", schema="public"):
        with op.batch_alter_table("stock_ledger", schema="public") as b:
            b.drop_column("location_id")

    # 2) snapshots: create v2 table (warehouse+item+batch), if not exists
    if not _table_exists(conn, "snapshots", schema="public"):
        op.create_table(
            "snapshots",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("warehouse_id", sa.Integer(), nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("batch_code", sa.String(length=64), nullable=False),
            sa.Column("qty_on_hand", sa.Integer(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["warehouse_id"], ["public.warehouses.id"], name="fk_snapshots_warehouse"),
            sa.ForeignKeyConstraint(["item_id"], ["public.items.id"], name="fk_snapshots_item"),
            # 不强制 FK 到 batches：批次字典可选（保持松耦合）
            schema="public",
        )

        # 唯一键，支撑 SnapshotService.run 的 ON CONFLICT
        if not _uc_exists(conn, "snapshots", "uq_snapshots_date_wh_item_code", schema="public"):
            op.create_unique_constraint(
                "uq_snapshots_date_wh_item_code",
                "snapshots",
                ["snapshot_date", "warehouse_id", "item_id", "batch_code"],
                schema="public",
            )

        # 实用索引（非必须）
        op.create_index("ix_snapshots_date", "snapshots", ["snapshot_date"], unique=False, schema="public")
        op.create_index("ix_snapshots_wh_item", "snapshots", ["warehouse_id", "item_id"], unique=False, schema="public")
        op.create_index("ix_snapshots_batch_code", "snapshots", ["batch_code"], unique=False, schema="public")

        # 可选：首日快照回填（仅当表为空时执行；来自 stocks 的现势余额）
        try:
            need_seed = conn.execute(sa.text("SELECT COUNT(1) FROM public.snapshots")).scalar() == 0
        except Exception:
            need_seed = False

        if need_seed and _table_exists(conn, "stocks", schema="public"):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO public.snapshots (snapshot_date, warehouse_id, item_id, batch_code, qty_on_hand)
                    SELECT CURRENT_DATE, s.warehouse_id, s.item_id, s.batch_code, COALESCE(s.qty_on_hand, 0)
                    FROM   public.stocks AS s
                    ON CONFLICT (snapshot_date, warehouse_id, item_id, batch_code)
                    DO NOTHING
                    """
                )
            )

    # 注意：旧表 public.stock_snapshots 不在本迁移中删除，后续统一清理


def downgrade():
    conn = op.get_bind()

    # 1) 尝试回滚 snapshots（仅在存在时）
    if _table_exists(conn, "snapshots", schema="public"):
        # 删除索引/约束
        for idx in ("ix_snapshots_date", "ix_snapshots_wh_item", "ix_snapshots_batch_code"):
            try:
                op.drop_index(idx, table_name="snapshots", schema="public")
            except Exception:
                pass
        try:
            op.drop_constraint("uq_snapshots_date_wh_item_code", "snapshots", type_="unique", schema="public")
        except Exception:
            pass
        try:
            op.drop_constraint("fk_snapshots_warehouse", "snapshots", type_="foreignkey", schema="public")
        except Exception:
            pass
        try:
            op.drop_constraint("fk_snapshots_item", "snapshots", type_="foreignkey", schema="public")
        except Exception:
            pass
        op.drop_table("snapshots", schema="public")

    # 2) 尝试恢复 stock_ledger.location_id（可选；仅示意）
    if not _col_exists(conn, "stock_ledger", "location_id", schema="public"):
        with op.batch_alter_table("stock_ledger", schema="public") as b:
            b.add_column(sa.Column("location_id", sa.Integer(), nullable=True))
