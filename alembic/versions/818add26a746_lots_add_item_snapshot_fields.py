"""lots: add item snapshot fields

Revision ID: 818add26a746
Revises: c95d0a9b73cd
Create Date: 2026-02-24 13:44:11.015352
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "818add26a746"
down_revision: Union[str, Sequence[str], None] = "c95d0a9b73cd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase 2: 冻结 item 侧关键主数据到 lots（snapshot），
    避免主数据变更污染历史 lot 解释链。
    """

    # ------------------------------------------------------------------
    # 1) 新增 snapshot 列（当前允许 NULL；Step 3 写入逻辑完成后再考虑收紧）
    # ------------------------------------------------------------------

    op.add_column(
        "lots",
        sa.Column("item_has_shelf_life_snapshot", sa.Boolean(), nullable=True),
    )

    op.add_column(
        "lots",
        sa.Column("item_shelf_life_value_snapshot", sa.Integer(), nullable=True),
    )
    op.add_column(
        "lots",
        sa.Column("item_shelf_life_unit_snapshot", sa.String(length=16), nullable=True),
    )

    op.add_column(
        "lots",
        sa.Column("item_uom_snapshot", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "lots",
        sa.Column("item_case_ratio_snapshot", sa.Integer(), nullable=True),
    )
    op.add_column(
        "lots",
        sa.Column("item_case_uom_snapshot", sa.String(length=16), nullable=True),
    )

    # ------------------------------------------------------------------
    # 2) 对齐 items 表的语义 CHECK
    # ------------------------------------------------------------------

    # 2.1) shelf_life_unit 枚举（DAY/WEEK/MONTH/YEAR）
    op.create_check_constraint(
        "ck_lots_item_shelf_life_unit_enum_snapshot",
        "lots",
        "("
        "item_shelf_life_unit_snapshot IS NULL OR "
        "item_shelf_life_unit_snapshot IN ('DAY','WEEK','MONTH','YEAR')"
        ")",
    )

    # 2.2) shelf_life_value/unit 必须成对出现
    op.create_check_constraint(
        "ck_lots_item_shelf_life_pair_snapshot",
        "lots",
        "((item_shelf_life_value_snapshot IS NULL) = "
        "(item_shelf_life_unit_snapshot IS NULL))",
    )

    # 2.3) 当 has_shelf_life=false 时，value/unit 必须为空
    op.create_check_constraint(
        "ck_lots_item_shelf_life_params_only_when_enabled_snapshot",
        "lots",
        "("
        "item_has_shelf_life_snapshot IS NULL OR "
        "item_has_shelf_life_snapshot = true OR "
        "(item_shelf_life_value_snapshot IS NULL AND "
        " item_shelf_life_unit_snapshot IS NULL)"
        ")",
    )

    # 2.4) case_ratio >= 1（对齐 items.ck_items_case_ratio_ge_1）
    op.create_check_constraint(
        "ck_lots_item_case_ratio_ge_1_snapshot",
        "lots",
        "(item_case_ratio_snapshot IS NULL OR "
        " item_case_ratio_snapshot >= 1)",
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 1) 先删 CHECK
    # ------------------------------------------------------------------
    op.drop_constraint(
        "ck_lots_item_case_ratio_ge_1_snapshot", "lots", type_="check"
    )
    op.drop_constraint(
        "ck_lots_item_shelf_life_params_only_when_enabled_snapshot",
        "lots",
        type_="check",
    )
    op.drop_constraint(
        "ck_lots_item_shelf_life_pair_snapshot",
        "lots",
        type_="check",
    )
    op.drop_constraint(
        "ck_lots_item_shelf_life_unit_enum_snapshot",
        "lots",
        type_="check",
    )

    # ------------------------------------------------------------------
    # 2) 再删列（逆序）
    # ------------------------------------------------------------------
    op.drop_column("lots", "item_case_uom_snapshot")
    op.drop_column("lots", "item_case_ratio_snapshot")
    op.drop_column("lots", "item_uom_snapshot")

    op.drop_column("lots", "item_shelf_life_unit_snapshot")
    op.drop_column("lots", "item_shelf_life_value_snapshot")
    op.drop_column("lots", "item_has_shelf_life_snapshot")
