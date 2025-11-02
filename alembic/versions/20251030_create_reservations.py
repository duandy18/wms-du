"""reservations: create table for batch-level reservations (idempotent)

- 创建 reservations 表（若不存在）：
  id BIGSERIAL PK
  order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE
  item_id  BIGINT NOT NULL
  batch_id BIGINT NOT NULL REFERENCES batches(id)
  qty      INTEGER NOT NULL
  reason   TEXT NOT NULL DEFAULT 'ORDER'
  ref      TEXT
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
- 索引：ix_reservations_order_id, ix_reservations_item_batch

Revision ID: 20251030_create_reservations
Revises: 20251030_orders_updated_at_default_now
Create Date: 2025-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "20251030_create_reservations"
down_revision = "20251030_orders_updated_at_default_now"  # ← 上一个已存在的 head
branch_labels = None
depends_on = None

def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.exec_driver_sql("""
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name='reservations'
        LIMIT 1
    """).scalar()
    if exists:
        return

    op.create_table(
        "reservations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), sa.ForeignKey("batches.id"), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=sa.text("'ORDER'")),
        sa.Column("ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_reservations_order_id", "reservations", ["order_id"], unique=False)
    op.create_index("ix_reservations_item_batch", "reservations", ["item_id", "batch_id"], unique=False)

def downgrade() -> None:
    conn = op.get_bind()
    exists = conn.exec_driver_sql("""
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name='reservations'
        LIMIT 1
    """).scalar()
    if exists:
        op.drop_index("ix_reservations_item_batch", table_name="reservations")
        op.drop_index("ix_reservations_order_id", table_name="reservations")
        op.drop_table("reservations")
