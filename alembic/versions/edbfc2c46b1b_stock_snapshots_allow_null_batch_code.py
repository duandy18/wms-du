"""stock_snapshots_allow_null_batch_code

Revision ID: edbfc2c46b1b
Revises: 16203ca6ea03
Create Date: 2026-02-01 23:24:13.728509

目的（严格单主线）：
- 让 stock_snapshots.batch_code 允许 NULL，用于表达“无批次”
- 引入生成列 batch_code_key = COALESCE(batch_code,'__NULL_BATCH__')
- 唯一性从 batch_code 迁移到 batch_code_key
- 与 stocks / stock_ledger 的 v3 世界观保持一致

注意：
- 不做任何历史数据修复（NOEXP / NEAR → NULL），那由 datafix 迁移负责
- 保持唯一约束名不变（uq_stock_snapshot_grain_v2），避免代码/SQL 漂移
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "edbfc2c46b1b"
down_revision: Union[str, Sequence[str], None] = "16203ca6ea03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------
    # 1) batch_code 允许 NULL
    # ------------------------------------------------------------
    op.alter_column(
        "stock_snapshots",
        "batch_code",
        existing_type=sa.String(length=64),
        nullable=True,
    )

    # ------------------------------------------------------------
    # 2) 添加生成列 batch_code_key
    # ------------------------------------------------------------
    op.add_column(
        "stock_snapshots",
        sa.Column(
            "batch_code_key",
            sa.String(length=64),
            sa.Computed("coalesce(batch_code, '__NULL_BATCH__')", persisted=True),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_stock_snapshots_batch_code_key",
        "stock_snapshots",
        ["batch_code_key"],
        unique=False,
    )

    # ------------------------------------------------------------
    # 3) 重建唯一约束（保持原约束名）
    #    原：(snapshot_date, warehouse_id, item_id, batch_code)
    #    新：(snapshot_date, warehouse_id, item_id, batch_code_key)
    # ------------------------------------------------------------
    op.drop_constraint(
        "uq_stock_snapshot_grain_v2",
        "stock_snapshots",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_stock_snapshot_grain_v2",
        "stock_snapshots",
        ["snapshot_date", "warehouse_id", "item_id", "batch_code_key"],
    )


def downgrade() -> None:
    # ------------------------------------------------------------
    # 回滚唯一约束：batch_code_key -> batch_code
    # ------------------------------------------------------------
    op.drop_constraint(
        "uq_stock_snapshot_grain_v2",
        "stock_snapshots",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_stock_snapshot_grain_v2",
        "stock_snapshots",
        ["snapshot_date", "warehouse_id", "item_id", "batch_code"],
    )

    # ------------------------------------------------------------
    # 移除 batch_code_key
    # ------------------------------------------------------------
    op.drop_index(
        "ix_stock_snapshots_batch_code_key",
        table_name="stock_snapshots",
    )
    op.drop_column("stock_snapshots", "batch_code_key")

    # ------------------------------------------------------------
    # 恢复 batch_code NOT NULL（旧世界观）
    # ------------------------------------------------------------
    op.alter_column(
        "stock_snapshots",
        "batch_code",
        existing_type=sa.String(length=64),
        nullable=False,
    )
