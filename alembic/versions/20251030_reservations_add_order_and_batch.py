"""reservations: add order_id & batch_id (idempotent)

为 reservations 增加批次绑定与订单绑定，便于按 order_id 预留、按批次回放/对账。
保持现有 status/ref 语义不变。

Revision ID: 20251030_reservations_add_order_and_batch
Revises: 20251030_add_batch_id_to_stocks
Create Date: 2025-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "20251030_reservations_add_order_and_batch"
down_revision = "20251030_add_batch_id_to_stocks"
branch_labels = None
depends_on = None

def _has_col(conn, table: str, col: str) -> bool:
    return bool(conn.exec_driver_sql("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        LIMIT 1
    """, (table, col)).scalar())

def upgrade():
    conn = op.get_bind()
    if not _has_col(conn, "reservations", "order_id"):
        op.add_column("reservations", sa.Column("order_id", sa.BigInteger(), nullable=True))
        op.create_index("ix_reservations_order_id", "reservations", ["order_id"], unique=False)
        # 若存在 orders 表，补外键（可延迟）
        conn.exec_driver_sql("""
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name='orders'
              ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_schema='public' AND table_name='reservations'
                  AND constraint_name='fk_reservations_order_id'
              ) THEN
                ALTER TABLE reservations
                  ADD CONSTRAINT fk_reservations_order_id
                  FOREIGN KEY (order_id) REFERENCES orders(id)
                  DEFERRABLE INITIALLY DEFERRED;
              END IF;
            END $$;
        """)

    if not _has_col(conn, "reservations", "batch_id"):
        op.add_column("reservations", sa.Column("batch_id", sa.BigInteger(), nullable=True))
        op.create_index("ix_reservations_batch_id", "reservations", ["batch_id"], unique=False)
        # 若存在 batches 表，补外键（可延迟）
        conn.exec_driver_sql("""
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name='batches'
              ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_schema='public' AND table_name='reservations'
                  AND constraint_name='fk_reservations_batch_id'
              ) THEN
                ALTER TABLE reservations
                  ADD CONSTRAINT fk_reservations_batch_id
                  FOREIGN KEY (batch_id) REFERENCES batches(id)
                  DEFERRABLE INITIALLY DEFERRED;
              END IF;
            END $$;
        """)

def downgrade():
    conn = op.get_bind()
    # 安全删除外键
    for cname in ("fk_reservations_order_id", "fk_reservations_batch_id"):
        conn.exec_driver_sql(f"""
            DO $$ BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_schema='public' AND table_name='reservations'
                  AND constraint_name='{cname}'
              ) THEN
                ALTER TABLE reservations DROP CONSTRAINT {cname};
              END IF;
            END $$;
        """)
    # 删索引与列（若存在）
    for ix in ("ix_reservations_order_id", "ix_reservations_batch_id"):
        conn.exec_driver_sql(f"DROP INDEX IF EXISTS {ix};")
    for col in ("order_id", "batch_id"):
        if _has_col(conn, "reservations", col):
            op.drop_column("reservations", col)
