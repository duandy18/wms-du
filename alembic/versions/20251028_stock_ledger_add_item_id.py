"""stock_ledger: add item_id (idempotent) + FK + index

Revision ID: 20251028_stock_ledger_add_item_id
Revises: 20251027_stock_snapshots_add_qty_columns
Create Date: 2025-10-28 10:22:00
"""
from alembic import op
import sqlalchemy as sa

# ---- identifiers ----
revision = "20251028_stock_ledger_add_item_id"
down_revision = "20251027_stock_snapshots_add_qty_columns"
branch_labels = None
depends_on = None

TABLE = "stock_ledger"
FK_NAME = "fk_stock_ledger_item_id"
IDX_TIME = "ix_stock_ledger_item_time"


def _col_exists(conn, table, col) -> bool:
    r = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t AND column_name=:c
            LIMIT 1
            """
        ),
        {"t": table, "c": col},
    ).scalar()
    return bool(r)


def _fk_exists(conn, table, name) -> bool:
    r = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid=c.conrelid
            WHERE t.relname=:t AND c.conname=:n AND c.contype='f'
            LIMIT 1
            """
        ),
        {"t": table, "n": name},
    ).scalar()
    return bool(r)


def _idx_exists(conn, name) -> bool:
    r = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_indexes
            WHERE schemaname='public' AND indexname=:n
            LIMIT 1
            """
        ),
        {"n": name},
    ).scalar()
    return bool(r)


def _null_count(conn, table, col) -> int:
    return int(
        conn.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL")
        ).scalar()
        or 0
    )


def upgrade():
    conn = op.get_bind()

    # 1) 列：若不存在则添加（先可空）
    if not _col_exists(conn, TABLE, "item_id"):
        op.add_column(TABLE, sa.Column("item_id", sa.Integer(), nullable=True))

    # 2) 回填 item_id（通过 stock_id -> stocks）
    #    只在仍有空值时做
    if _null_count(conn, TABLE, "item_id") > 0:
        op.execute(
            """
            UPDATE stock_ledger l
            SET item_id = s.item_id
            FROM stocks s
            WHERE l.stock_id = s.id AND l.item_id IS NULL
            """
        )

    # 3) 设为 NOT NULL（仅当无空值时）
    if _null_count(conn, TABLE, "item_id") == 0:
        op.alter_column(TABLE, "item_id", nullable=False)

    # 4) 外键（若不存在则添加）
    if not _fk_exists(conn, TABLE, FK_NAME):
        op.create_foreign_key(
            FK_NAME,
            TABLE,
            "items",
            ["item_id"],
            ["id"],
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        )

    # 5) 索引（若不存在则添加）
    if not _idx_exists(conn, IDX_TIME):
        op.create_index(IDX_TIME, TABLE, ["item_id", "occurred_at"])


def downgrade():
    conn = op.get_bind()
    # 逆序：索引 -> 外键 -> 列
    if _idx_exists(conn, IDX_TIME):
        op.drop_index(IDX_TIME, table_name=TABLE)
    if _fk_exists(conn, TABLE, FK_NAME):
        op.drop_constraint(FK_NAME, TABLE, type_="foreignkey")
    if _col_exists(conn, TABLE, "item_id"):
        op.drop_column(TABLE, "item_id")
