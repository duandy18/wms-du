"""batches_stocks_v3_worldview

Revision ID: 6b578e4ca158
Revises: e93b47e8b6b2
Create Date: 2025-12-07 17:15:51.325718

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6b578e4ca158"
down_revision: Union[str, Sequence[str], None] = "e93b47e8b6b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Finalize batches/stocks to v3 worldview: (warehouse_id, item_id, batch_code)."""
    conn = op.get_bind()

    # ---------- Helpers ----------
    def has_column(table: str, column: str) -> bool:
        return conn.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :t
                  AND column_name = :c
                """
            ),
            {"t": table, "c": column},
        ).scalar() is not None

    def has_constraint(table: str, name: str) -> bool:
        return conn.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_schema = 'public'
                  AND table_name = :t
                  AND constraint_name = :n
                """
            ),
            {"t": table, "n": name},
        ).scalar() is not None

    # ==========================================
    # 1) batches 补全 / 统一到 (warehouse_id, item_id, batch_code)
    # ==========================================
    if not has_column("batches", "warehouse_id"):
        op.add_column(
            "batches",
            sa.Column("warehouse_id", sa.Integer(), nullable=True),
        )
        # 中试 / 测试库：缺失的先统一丢到仓库 1
        conn.execute(
            sa.text("UPDATE batches SET warehouse_id = 1 WHERE warehouse_id IS NULL")
        )
        op.alter_column("batches", "warehouse_id", nullable=False)

    # 删除旧的 (item_id, batch_code) 级别唯一约束（尝试几种常见命名）
    old_batch_constraints = [
        "uq_batches_item_batch",
        "uq_batches_item_code",
        "uq_batches_itemid_batchcode",
    ]
    for cname in old_batch_constraints:
        if has_constraint("batches", cname):
            op.drop_constraint(cname, "batches", type_="unique")

    # 建立新的 v3 唯一约束
    if not has_constraint("batches", "uq_batches_wh_item_code"):
        op.create_unique_constraint(
            "uq_batches_wh_item_code",
            "batches",
            ["warehouse_id", "item_id", "batch_code"],
        )

    # 创建索引（如果不存在）
    conn.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'batches'
                  AND indexname = 'ix_batches_wh_item_code'
              ) THEN
                CREATE INDEX ix_batches_wh_item_code
                  ON batches (warehouse_id, item_id, batch_code);
              END IF;
            END$$;
            """
        )
    )

    # 在触碰 stocks 之前，把所有延迟约束提前结算掉，避免 "pending trigger events"
    conn.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))

    # ==========================================
    # 2) stocks 补全 / 统一到 (warehouse_id, item_id, batch_code)
    # ==========================================
    if not has_column("stocks", "warehouse_id"):
        op.add_column(
            "stocks",
            sa.Column("warehouse_id", sa.Integer(), nullable=True),
        )
        conn.execute(
            sa.text("UPDATE stocks SET warehouse_id = 1 WHERE warehouse_id IS NULL")
        )
        op.alter_column("stocks", "warehouse_id", nullable=False)

    old_stock_constraints = [
        "uq_stocks_item_batch",
        "uq_stocks_item_code",
        "uq_stocks_itemid_batchcode",
    ]
    for cname in old_stock_constraints:
        if has_constraint("stocks", cname):
            op.drop_constraint(cname, "stocks", type_="unique")

    if not has_constraint("stocks", "uq_stocks_wh_item_code"):
        op.create_unique_constraint(
            "uq_stocks_wh_item_code",
            "stocks",
            ["warehouse_id", "item_id", "batch_code"],
        )

    conn.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'stocks'
                  AND indexname = 'ix_stocks_wh_item_code'
              ) THEN
                CREATE INDEX ix_stocks_wh_item_code
                  ON stocks (warehouse_id, item_id, batch_code);
              END IF;
            END$$;
            """
        )
    )


def downgrade() -> None:
    """Best-effort downgrade: drop v3 unique constraints and indexes."""
    conn = op.get_bind()

    def has_constraint(table: str, name: str) -> bool:
        return conn.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_schema = 'public'
                  AND table_name = :t
                  AND constraint_name = :n
                """
            ),
            {"t": table, "n": name},
        ).scalar() is not None

    # batches: drop v3 UQ
    if has_constraint("batches", "uq_batches_wh_item_code"):
        op.drop_constraint("uq_batches_wh_item_code", "batches", type_="unique")

    # batches: drop index（如果存在）
    conn.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'batches'
                  AND indexname = 'ix_batches_wh_item_code'
              ) THEN
                DROP INDEX ix_batches_wh_item_code;
              END IF;
            END$$;
            """
        )
    )

    # stocks: drop v3 UQ
    if has_constraint("stocks", "uq_stocks_wh_item_code"):
        op.drop_constraint("uq_stocks_wh_item_code", "stocks", type_="unique")

    # stocks: drop index
    conn.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'stocks'
                  AND indexname = 'ix_stocks_wh_item_code'
              ) THEN
                DROP INDEX ix_stocks_wh_item_code;
              END IF;
            END$$;
            """
        )
    )
