"""stocks_ledger_allow_null_batch_code

Revision ID: 3a5761b8cbd5
Revises: 1cc94f14a0fa
Create Date: 2026-02-01 20:55:10.775026

本迁移的唯一目标（严格单主线）：
- 让 stocks.batch_code / stock_ledger.batch_code 支持 NULL 来表达“无批次”
- 用生成列 batch_code_key = coalesce(batch_code, '__NULL_BATCH__') 参与唯一性
  以保证：
  1) 同一 (item_id, warehouse_id) 下只存在一个 NULL 槽位
  2) ledger 幂等键对 NULL 同样成立
  3) 继续沿用原约束名，便于 ON CONFLICT(constraint=...) 稳定工作

注意：
- 本迁移不做历史数据清洗（例如 NOEXP → NULL），那是下一步 datafix。
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3a5761b8cbd5"
down_revision: Union[str, Sequence[str], None] = "1cc94f14a0fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # -----------------------------
    # stocks：允许 batch_code 为 NULL + 生成列 batch_code_key + 重建唯一约束
    # -----------------------------
    op.alter_column(
        "stocks",
        "batch_code",
        existing_type=sa.String(length=64),
        nullable=True,
    )

    # 生成列：coalesce(batch_code, '__NULL_BATCH__')
    op.add_column(
        "stocks",
        sa.Column(
            "batch_code_key",
            sa.String(length=64),
            sa.Computed("coalesce(batch_code, '__NULL_BATCH__')", persisted=True),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_stocks_batch_code_key",
        "stocks",
        ["batch_code_key"],
        unique=False,
    )

    # 原约束 uq_stocks_item_wh_batch 目前在 ORM 中是 (item_id, warehouse_id, batch_code)
    # 允许 NULL 后该约束对 NULL 不再“唯一”，因此重建为 (item_id, warehouse_id, batch_code_key)
    op.drop_constraint("uq_stocks_item_wh_batch", "stocks", type_="unique")
    op.create_unique_constraint(
        "uq_stocks_item_wh_batch",
        "stocks",
        ["item_id", "warehouse_id", "batch_code_key"],
    )

    # -----------------------------
    # stock_ledger：允许 batch_code 为 NULL + 生成列 batch_code_key + 重建幂等唯一约束
    # -----------------------------
    op.alter_column(
        "stock_ledger",
        "batch_code",
        existing_type=sa.String(length=64),
        nullable=True,
    )

    op.add_column(
        "stock_ledger",
        sa.Column(
            "batch_code_key",
            sa.String(length=64),
            sa.Computed("coalesce(batch_code, '__NULL_BATCH__')", persisted=True),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_stock_ledger_batch_code_key",
        "stock_ledger",
        ["batch_code_key"],
        unique=False,
    )

    # 原约束 uq_ledger_wh_batch_item_reason_ref_line 目前包含 batch_code（NOT NULL）
    # 允许 NULL 后，为保持幂等稳定，改为使用 batch_code_key
    # 并保持约束名不变，确保 ledger_writer 仍可 ON CONFLICT(constraint=...)。
    op.drop_constraint("uq_ledger_wh_batch_item_reason_ref_line", "stock_ledger", type_="unique")
    op.create_unique_constraint(
        "uq_ledger_wh_batch_item_reason_ref_line",
        "stock_ledger",
        ["reason", "ref", "ref_line", "item_id", "batch_code_key", "warehouse_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""

    # -----------------------------
    # stock_ledger 回滚：恢复旧幂等唯一约束（用 batch_code）并恢复 batch_code NOT NULL
    # -----------------------------
    op.drop_constraint("uq_ledger_wh_batch_item_reason_ref_line", "stock_ledger", type_="unique")
    op.create_unique_constraint(
        "uq_ledger_wh_batch_item_reason_ref_line",
        "stock_ledger",
        ["reason", "ref", "ref_line", "item_id", "batch_code", "warehouse_id"],
    )

    op.drop_index("ix_stock_ledger_batch_code_key", table_name="stock_ledger")
    op.drop_column("stock_ledger", "batch_code_key")

    op.alter_column(
        "stock_ledger",
        "batch_code",
        existing_type=sa.String(length=64),
        nullable=False,
    )

    # -----------------------------
    # stocks 回滚：恢复旧唯一约束（用 batch_code）并恢复 batch_code NOT NULL
    # -----------------------------
    op.drop_constraint("uq_stocks_item_wh_batch", "stocks", type_="unique")
    op.create_unique_constraint(
        "uq_stocks_item_wh_batch",
        "stocks",
        ["item_id", "warehouse_id", "batch_code"],
    )

    op.drop_index("ix_stocks_batch_code_key", table_name="stocks")
    op.drop_column("stocks", "batch_code_key")

    op.alter_column(
        "stocks",
        "batch_code",
        existing_type=sa.String(length=64),
        nullable=False,
    )
