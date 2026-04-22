"""inventory_adjustment_count_doc_lines_add_uom_snapshots_and_base_qtys

Revision ID: 265fe9d55bbd
Revises: 8d4ecaaae5d4
Create Date: 2026-04-22 14:07:12.042335

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "265fe9d55bbd"
down_revision: Union[str, Sequence[str], None] = "8d4ecaaae5d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ------------------------------------------------------------------
    # count_doc_lines 第二刀：
    # 1) 数量字段显式收紧到 base 语义
    # 2) 补盘点包装单位 / 倍率 / 输入数量 / 商品展示快照
    #
    # 终态口径：
    # - snapshot_qty_base：冻结时点库存（基础数量）
    # - counted_qty_input：按盘点包装单位录入的数量
    # - counted_ratio_to_base_snapshot：盘点时冻结的倍率快照
    # - counted_qty_base：换算后的基础数量
    # - diff_qty_base：counted_qty_base - snapshot_qty_base
    # ------------------------------------------------------------------

    # 先删旧约束（旧约束名仍基于旧列名）
    op.drop_constraint(
        "ck_count_doc_lines_counted_qty_nonneg",
        "count_doc_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_count_doc_lines_diff_consistent",
        "count_doc_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_count_doc_lines_snapshot_qty_nonneg",
        "count_doc_lines",
        type_="check",
    )

    # 数量列改名：明确 base 语义
    op.alter_column(
        "count_doc_lines",
        "snapshot_qty",
        new_column_name="snapshot_qty_base",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "count_doc_lines",
        "counted_qty",
        new_column_name="counted_qty_base",
        existing_type=sa.Integer(),
        existing_nullable=True,
    )
    op.alter_column(
        "count_doc_lines",
        "diff_qty",
        new_column_name="diff_qty_base",
        existing_type=sa.Integer(),
        existing_nullable=True,
    )

    # 商品展示快照
    op.add_column(
        "count_doc_lines",
        sa.Column("item_name_snapshot", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "count_doc_lines",
        sa.Column("item_spec_snapshot", sa.String(length=255), nullable=True),
    )

    # 盘点包装单位 / 倍率 / 输入数量
    op.add_column(
        "count_doc_lines",
        sa.Column("counted_item_uom_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "count_doc_lines",
        sa.Column("counted_uom_name_snapshot", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "count_doc_lines",
        sa.Column("counted_ratio_to_base_snapshot", sa.Integer(), nullable=True),
    )
    op.add_column(
        "count_doc_lines",
        sa.Column("counted_qty_input", sa.Integer(), nullable=True),
    )

    op.create_foreign_key(
        "fk_count_doc_lines_counted_item_uom",
        "count_doc_lines",
        "item_uoms",
        ["counted_item_uom_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_count_doc_lines_counted_item_uom_id",
        "count_doc_lines",
        ["counted_item_uom_id"],
        unique=False,
    )

    # 新约束：全部以 base 语义为准
    op.create_check_constraint(
        "ck_count_doc_lines_snapshot_qty_base_nonneg",
        "count_doc_lines",
        "snapshot_qty_base >= 0",
    )
    op.create_check_constraint(
        "ck_count_doc_lines_counted_qty_input_nonneg",
        "count_doc_lines",
        "counted_qty_input IS NULL OR counted_qty_input >= 0",
    )
    op.create_check_constraint(
        "ck_count_doc_lines_counted_qty_base_nonneg",
        "count_doc_lines",
        "counted_qty_base IS NULL OR counted_qty_base >= 0",
    )
    op.create_check_constraint(
        "ck_count_doc_lines_counted_ratio_positive",
        "count_doc_lines",
        "counted_ratio_to_base_snapshot IS NULL OR counted_ratio_to_base_snapshot >= 1",
    )

    op.create_check_constraint(
        "ck_count_doc_lines_count_payload_consistent",
        "count_doc_lines",
        """
        (
          counted_item_uom_id IS NULL
          AND counted_uom_name_snapshot IS NULL
          AND counted_ratio_to_base_snapshot IS NULL
          AND counted_qty_input IS NULL
          AND counted_qty_base IS NULL
          AND diff_qty_base IS NULL
        )
        OR
        (
          counted_item_uom_id IS NOT NULL
          AND counted_uom_name_snapshot IS NOT NULL
          AND counted_ratio_to_base_snapshot IS NOT NULL
          AND counted_qty_input IS NOT NULL
          AND counted_qty_base IS NOT NULL
          AND diff_qty_base IS NOT NULL
          AND counted_qty_base = (counted_qty_input * counted_ratio_to_base_snapshot)
          AND diff_qty_base = (counted_qty_base - snapshot_qty_base)
        )
        """,
    )


def downgrade() -> None:
    """Downgrade schema."""

    # 先删新约束 / 索引 / FK
    op.drop_constraint(
        "ck_count_doc_lines_count_payload_consistent",
        "count_doc_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_count_doc_lines_counted_ratio_positive",
        "count_doc_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_count_doc_lines_counted_qty_base_nonneg",
        "count_doc_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_count_doc_lines_counted_qty_input_nonneg",
        "count_doc_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_count_doc_lines_snapshot_qty_base_nonneg",
        "count_doc_lines",
        type_="check",
    )

    op.drop_index(
        "ix_count_doc_lines_counted_item_uom_id",
        table_name="count_doc_lines",
    )
    op.drop_constraint(
        "fk_count_doc_lines_counted_item_uom",
        "count_doc_lines",
        type_="foreignkey",
    )

    # 删新增列
    op.drop_column("count_doc_lines", "counted_qty_input")
    op.drop_column("count_doc_lines", "counted_ratio_to_base_snapshot")
    op.drop_column("count_doc_lines", "counted_uom_name_snapshot")
    op.drop_column("count_doc_lines", "counted_item_uom_id")
    op.drop_column("count_doc_lines", "item_spec_snapshot")
    op.drop_column("count_doc_lines", "item_name_snapshot")

    # 列名改回旧语义
    op.alter_column(
        "count_doc_lines",
        "diff_qty_base",
        new_column_name="diff_qty",
        existing_type=sa.Integer(),
        existing_nullable=True,
    )
    op.alter_column(
        "count_doc_lines",
        "counted_qty_base",
        new_column_name="counted_qty",
        existing_type=sa.Integer(),
        existing_nullable=True,
    )
    op.alter_column(
        "count_doc_lines",
        "snapshot_qty_base",
        new_column_name="snapshot_qty",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # 恢复旧约束
    op.create_check_constraint(
        "ck_count_doc_lines_snapshot_qty_nonneg",
        "count_doc_lines",
        "snapshot_qty >= 0",
    )
    op.create_check_constraint(
        "ck_count_doc_lines_counted_qty_nonneg",
        "count_doc_lines",
        "counted_qty IS NULL OR counted_qty >= 0",
    )
    op.create_check_constraint(
        "ck_count_doc_lines_diff_consistent",
        "count_doc_lines",
        """
        (
          (counted_qty IS NULL AND diff_qty IS NULL)
          OR
          (counted_qty IS NOT NULL AND diff_qty = (counted_qty - snapshot_qty))
        )
        """,
    )
