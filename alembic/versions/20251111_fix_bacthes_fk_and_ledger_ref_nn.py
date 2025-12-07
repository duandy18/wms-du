"""v2 fix(2): ensure batches FK and ledger.ref NOT NULL

Revision ID: 20251111_fix_bacthes_fk_and_ledger_ref_nn
Revises: 20251111_fix_fk_and_ref_not_null
Create Date: 2025-11-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# IDs
revision = "20251111_fix_bacthes_fk_and_ledger_ref_nn"
down_revision = "20251111_fix_fk_and_ref_not_null"
branch_labels = None
depends_on = None


def _has_fk(conn, table: str, constraint_name: str = None, col: str = None, referred_table: str = None) -> bool:
    insp = Inspector.from_engine(conn)
    fks = insp.get_foreign_keys(table, schema="public")
    if constraint_name:
        return any(fk.get("name") == constraint_name for fk in fks)
    if col and referred_table:
        for fk in fks:
            if fk.get("referred_table") == referred_table and fk.get("constrained_columns") == [col]:
                return True
    return False


def upgrade():
    conn = op.get_bind()

    # 1) stock_ledger.ref → NOT NULL（先兜底回填空值）
    conn.execute(sa.text("""
        UPDATE public.stock_ledger
           SET ref = 'MIGR-' || id
         WHERE ref IS NULL
    """))
    # 再强制非空（若已是 NOT NULL，此操作将是幂等）
    op.alter_column(
        "stock_ledger",
        "ref",
        existing_type=sa.String(length=128),
        nullable=False,
        schema="public",
        existing_nullable=True  # 提示当前可能为可空；若已非空也无碍
    )

    # 2) batches.item_id → items(id) 外键（如果缺失则创建）
    if not _has_fk(conn, table="batches", col="item_id", referred_table="items"):
        op.create_foreign_key(
            "fk_batches_item",                # 约束名
            "batches",                        # 源表
            "items",                          # 参照表
            ["item_id"],                      # 源列
            ["id"],                           # 参照列
            source_schema="public",
            referent_schema="public",
            ondelete=None
        )


def downgrade():
    conn = op.get_bind()

    # 还原 stock_ledger.ref 可空（可选）
    op.alter_column(
        "stock_ledger",
        "ref",
        existing_type=sa.String(length=128),
        nullable=True,
        schema="public"
    )

    # 删除 batches 外键（如存在）
    if _has_fk(conn, table="batches", constraint_name="fk_batches_item"):
        op.drop_constraint("fk_batches_item", "batches", type_="foreignkey", schema="public")
