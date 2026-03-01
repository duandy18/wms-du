"""phase_m4_lot_snapshot_rename_stage1

Revision ID: f873b9849c38
Revises: b544bf322a3d
Create Date: 2026-03-01 11:07:59.330684

M-4（可选）第三项：lot snapshot 命名收敛 —— Stage1（新增列 + 回填）

新增：
- item_base_uom_snapshot
- item_purchase_ratio_snapshot
- item_purchase_uom_snapshot

回填：
- item_base_uom_snapshot <- item_uom_snapshot
- item_purchase_* <- item_case_*（当前可能为 NULL，保持 NULL）

约束：
- ck_lots_item_purchase_ratio_ge_1_snapshot：NULL 或 >=1

Stage1 不删除旧列/旧 check（Stage2 处理）。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f873b9849c38"
down_revision: Union[str, Sequence[str], None] = "b544bf322a3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("lots") as bop:
        bop.add_column(sa.Column("item_base_uom_snapshot", sa.String(length=8), nullable=True))
        bop.add_column(sa.Column("item_purchase_ratio_snapshot", sa.Integer(), nullable=True))
        bop.add_column(sa.Column("item_purchase_uom_snapshot", sa.String(length=16), nullable=True))

    op.execute(
        """
        UPDATE lots
           SET item_base_uom_snapshot = item_uom_snapshot
         WHERE item_base_uom_snapshot IS NULL
           AND item_uom_snapshot IS NOT NULL
        """
    )

    op.execute(
        """
        UPDATE lots
           SET item_purchase_ratio_snapshot = item_case_ratio_snapshot,
               item_purchase_uom_snapshot   = item_case_uom_snapshot
         WHERE item_purchase_ratio_snapshot IS NULL
           AND item_purchase_uom_snapshot IS NULL
        """
    )

    op.execute(
        """
        ALTER TABLE lots
        ADD CONSTRAINT ck_lots_item_purchase_ratio_ge_1_snapshot
        CHECK (item_purchase_ratio_snapshot IS NULL OR item_purchase_ratio_snapshot >= 1)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE lots DROP CONSTRAINT IF EXISTS ck_lots_item_purchase_ratio_ge_1_snapshot")

    with op.batch_alter_table("lots") as bop:
        bop.drop_column("item_purchase_uom_snapshot")
        bop.drop_column("item_purchase_ratio_snapshot")
        bop.drop_column("item_base_uom_snapshot")
