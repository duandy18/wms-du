"""perf indexes for fefo & ledger queries

Revision ID: 20251014_perf_indexes
Revises:
Create Date: 2025-10-14
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251014_perf_indexes"
down_revision = None
branch_labels = None
depends_on = None


def _is_pg() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names(schema=None)


def upgrade():
    """
    只在 PostgreSQL 上并发建索引；且仅当目标表已存在时才执行。
    使用 Alembic 的 autocommit_block() 以允许 CONCURRENTLY。
    """
    if not _is_pg():
        return

    ctx = op.get_context()
    with ctx.autocommit_block():
        # FEFO 索引：batches(item_id, expiry_date)
        if _has_table("batches"):
            try:
                op.create_index(
                    "ix_batches_fefo",
                    "batches",
                    ["item_id", "expiry_date"],
                    unique=False,
                    postgresql_concurrently=True,
                    if_not_exists=True,
                )
            except TypeError:
                # 兼容旧 Alembic（无 if_not_exists）
                op.create_index(
                    "ix_batches_fefo",
                    "batches",
                    ["item_id", "expiry_date"],
                    unique=False,
                    postgresql_concurrently=True,
                )

        # Ledger 热路径索引：stock_ledger(stock_id, occurred_at)
        # 注意：真实表名为 stock_ledger（而非 ledger），且没有 item_id/location_id 两列
        if _has_table("stock_ledger"):
            try:
                op.create_index(
                    "ix_ledger_stock_ts",
                    "stock_ledger",
                    ["stock_id", "occurred_at"],
                    unique=False,
                    postgresql_concurrently=True,
                    if_not_exists=True,
                )
            except TypeError:
                op.create_index(
                    "ix_ledger_stock_ts",
                    "stock_ledger",
                    ["stock_id", "occurred_at"],
                    unique=False,
                    postgresql_concurrently=True,
                )


def downgrade():
    if not _is_pg():
        return

    ctx = op.get_context()
    with ctx.autocommit_block():
        if _has_table("stock_ledger"):
            try:
                op.drop_index(
                    "ix_ledger_stock_ts",
                    table_name="stock_ledger",
                    postgresql_concurrently=True,
                    if_exists=True,
                )
            except TypeError:
                op.drop_index(
                    "ix_ledger_stock_ts",
                    table_name="stock_ledger",
                    postgresql_concurrently=True,
                )

        if _has_table("batches"):
            try:
                op.drop_index(
                    "ix_batches_fefo",
                    table_name="batches",
                    postgresql_concurrently=True,
                    if_exists=True,
                )
            except TypeError:
                op.drop_index(
                    "ix_batches_fefo",
                    table_name="batches",
                    postgresql_concurrently=True,
                )
