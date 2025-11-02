"""reservations: create table for batch-level reservations (idempotent)

Revision ID: 20251030_create_reservations
Revises: 20251030_orders_updated_at_default_now
Create Date: 2025-10-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# ---- Alembic identifiers ----
revision = "20251030_create_reservations"
down_revision = "20251030_orders_updated_at_default_now"
branch_labels = None
depends_on = None


# ---------------- helpers: idempotent checks (仅供 upgrade 使用) ----------------
def _insp():
    bind = op.get_bind()
    return sa.inspect(bind)

def _has_table(name: str) -> bool:
    return _insp().has_table(name)

def _has_column(table: str, column: str) -> bool:
    try:
        return any(c["name"] == column for c in _insp().get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    # 1) 表不存在则创建（标准形态）
    if not _has_table("reservations"):
        op.create_table(
            "reservations",
            sa.Column("id", sa.BigInteger, primary_key=True),
            sa.Column("order_id", sa.BigInteger, nullable=True),
            sa.Column("item_id", sa.BigInteger, nullable=False),
            sa.Column("batch_id", sa.BigInteger, nullable=True),
            sa.Column("qty", sa.Numeric(18, 6), nullable=False),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    else:
        # 2) 表已存在：逐列补齐缺失列（幂等）
        if not _has_column("reservations", "order_id"):
            op.add_column("reservations", sa.Column("order_id", sa.BigInteger, nullable=True))
        if not _has_column("reservations", "item_id"):
            op.add_column("reservations", sa.Column("item_id", sa.BigInteger, nullable=False))
        if not _has_column("reservations", "batch_id"):
            op.add_column("reservations", sa.Column("batch_id", sa.BigInteger, nullable=True))
        if not _has_column("reservations", "qty"):
            op.add_column("reservations", sa.Column("qty", sa.Numeric(18, 6), nullable=False, server_default=sa.text("0")))
            op.alter_column("reservations", "qty", server_default=None)
        if not _has_column("reservations", "created_at"):
            op.add_column(
                "reservations",
                sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            )

    # 3) 仅对“确实已存在”的列创建索引 —— 使用 DO $$ + information_schema 判定，避免反射缓存
    conn = op.get_bind()

    # order_id
    conn.execute(sa.text("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='reservations' AND column_name='order_id'
      ) THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS ix_reservations_order_id ON public.reservations (order_id)';
      END IF;
    END$$;"""))

    # item_id
    conn.execute(sa.text("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='reservations' AND column_name='item_id'
      ) THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS ix_reservations_item_id ON public.reservations (item_id)';
      END IF;
    END$$;"""))

    # batch_id
    conn.execute(sa.text("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='reservations' AND column_name='batch_id'
      ) THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS ix_reservations_batch_id ON public.reservations (batch_id)';
      END IF;
    END$$;"""))

    # 组合索引 (item_id, batch_id) —— 历史兼容
    conn.execute(sa.text("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='reservations' AND column_name='item_id'
      )
      AND EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='reservations' AND column_name='batch_id'
      )
      THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS ix_reservations_item_batch ON public.reservations (item_id, batch_id)';
      END IF;
    END$$;"""))

    # 外键（如需要；按需开启）
    # …（略）


def downgrade() -> None:
    """
    纯 DDL，一条 CASCADE 即可；避免反射与多步 DDL 导致事务失败串联。
    """
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS public.reservations CASCADE"))
