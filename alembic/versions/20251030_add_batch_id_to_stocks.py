"""stocks: add batch_id FK to batches (idempotent, no backfill)

为 stocks 增加 batch_id（指向 batches.id），用于批次级 onhand 统计与 FEFO 分摊。
本迁移不回填历史数据；测试/新写入由业务层（StockService.adjust）写入 batch_id。

Revision ID: 20251030_add_batch_id_to_stocks
Revises: 20251030_create_reservations
Create Date: 2025-10-30
"""

from alembic import op
import sqlalchemy as sa

revision = "20251030_add_batch_id_to_stocks"
down_revision = "20251030_create_reservations"  # ← 现在指向刚才那条
branch_labels = None
depends_on = None


def _has_col(conn, table: str, col: str) -> bool:
    return bool(
        conn.exec_driver_sql(
            """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        LIMIT 1
        """,
            (table, col),
        ).scalar()
    )


def upgrade() -> None:
    conn = op.get_bind()

    # 1) 增加 batch_id（若不存在）
    if not _has_col(conn, "stocks", "batch_id"):
        op.add_column("stocks", sa.Column("batch_id", sa.BigInteger(), nullable=True))

    # 2) 建索引（若不存在）
    op.create_index("ix_stocks_batch_id", "stocks", ["batch_id"], unique=False)

    # 3) 外键（若不存在）
    conn.exec_driver_sql("""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_schema='public' AND table_name='stocks' AND constraint_type='FOREIGN KEY'
                  AND constraint_name='fk_stocks_batch_id'
          ) THEN
            ALTER TABLE stocks
            ADD CONSTRAINT fk_stocks_batch_id
            FOREIGN KEY (batch_id) REFERENCES batches(id)
            DEFERRABLE INITIALLY DEFERRED;
          END IF;
        END
        $$;
    """)


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_schema='public' AND table_name='stocks' AND constraint_type='FOREIGN KEY'
                  AND constraint_name='fk_stocks_batch_id'
          ) THEN
            ALTER TABLE stocks DROP CONSTRAINT fk_stocks_batch_id;
          END IF;
        END
        $$;
    """)
    op.drop_index("ix_stocks_batch_id", table_name="stocks")
    if _has_col(conn, "stocks", "batch_id"):
        op.drop_column("stocks", "batch_id")
