"""phase_m4_lot_snapshot_rename_stage3_drop_legacy_case

Revision ID: baef8c90d4ea
Revises: f873b9849c38
Create Date: 2026-03-01 11:19:50.602186

M-4（可选）第三项：lot snapshot 命名收敛 —— Stage3（删除旧列/旧约束）

删除 legacy 列（历史 “case” 术语残影）：
- lots.item_uom_snapshot
- lots.item_case_ratio_snapshot
- lots.item_case_uom_snapshot

删除 legacy check：
- ck_lots_item_case_ratio_ge_1_snapshot

保留新列：
- lots.item_base_uom_snapshot
- lots.item_purchase_ratio_snapshot
- lots.item_purchase_uom_snapshot

保留新 check：
- ck_lots_item_purchase_ratio_ge_1_snapshot
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "baef8c90d4ea"
down_revision: Union[str, Sequence[str], None] = "f873b9849c38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) drop legacy check first (avoid dependency issues)
    op.execute("ALTER TABLE lots DROP CONSTRAINT IF EXISTS ck_lots_item_case_ratio_ge_1_snapshot")

    # 2) drop legacy columns
    with op.batch_alter_table("lots") as bop:
        bop.drop_column("item_case_uom_snapshot")
        bop.drop_column("item_case_ratio_snapshot")
        bop.drop_column("item_uom_snapshot")


def downgrade() -> None:
    # Re-create legacy columns (best-effort rollback)
    with op.batch_alter_table("lots") as bop:
        bop.add_column(sa.Column("item_uom_snapshot", sa.String(length=8), nullable=True))
        bop.add_column(sa.Column("item_case_ratio_snapshot", sa.Integer(), nullable=True))
        bop.add_column(sa.Column("item_case_uom_snapshot", sa.String(length=16), nullable=True))

    op.execute(
        """
        ALTER TABLE lots
        ADD CONSTRAINT ck_lots_item_case_ratio_ge_1_snapshot
        CHECK (item_case_ratio_snapshot IS NULL OR item_case_ratio_snapshot >= 1)
        """
    )

    # Backfill legacy columns from new semantic columns (for rollback readability)
    op.execute(
        """
        UPDATE lots
           SET item_uom_snapshot = item_base_uom_snapshot
         WHERE item_uom_snapshot IS NULL
           AND item_base_uom_snapshot IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE lots
           SET item_case_ratio_snapshot = item_purchase_ratio_snapshot,
               item_case_uom_snapshot   = item_purchase_uom_snapshot
         WHERE item_case_ratio_snapshot IS NULL
           AND item_case_uom_snapshot IS NULL
        """
    )
