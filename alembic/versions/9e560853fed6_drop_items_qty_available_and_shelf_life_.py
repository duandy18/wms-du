"""drop items.qty_available and shelf_life_days; harden shelf-life contract

Revision ID: 9e560853fed6
Revises: b143e6f27641
Create Date: 2026-02-16 22:09:22.214864
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9e560853fed6"
down_revision: Union[str, Sequence[str], None] = "b143e6f27641"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------
    # 0) 数据归一：防止历史脏值导致新增约束失败
    # ------------------------------------------------------------

    # unit 空字符串 / 'none' 归一为 NULL
    op.execute(
        """
        UPDATE items
           SET shelf_life_unit = NULL
         WHERE shelf_life_unit IS NOT NULL
           AND (btrim(shelf_life_unit) = '' OR lower(btrim(shelf_life_unit)) = 'none');
        """
    )

    # has_shelf_life=false 时，不应携带保质期参数
    op.execute(
        """
        UPDATE items
           SET shelf_life_value = NULL,
               shelf_life_unit  = NULL
         WHERE has_shelf_life = false;
        """
    )

    # value/unit 成对：只要有一边为空，就都置空
    op.execute(
        """
        UPDATE items
           SET shelf_life_value = NULL,
               shelf_life_unit  = NULL
         WHERE (shelf_life_value IS NULL) <> (shelf_life_unit IS NULL);
        """
    )

    # ------------------------------------------------------------
    # 1) 删除历史字段
    # ------------------------------------------------------------
    op.drop_column("items", "qty_available")
    op.drop_column("items", "shelf_life_days")

    # ------------------------------------------------------------
    # 2) 加强保质期参数合同（DB 层护栏）
    # ------------------------------------------------------------

    # value/unit 必须同时为空或同时非空
    op.create_check_constraint(
        "ck_items_shelf_life_pair",
        "items",
        "(shelf_life_value IS NULL) = (shelf_life_unit IS NULL)",
    )

    # value > 0（仅当存在时）
    op.create_check_constraint(
        "ck_items_shelf_life_value_pos",
        "items",
        "shelf_life_value IS NULL OR shelf_life_value > 0",
    )

    # unit 合法枚举
    op.create_check_constraint(
        "ck_items_shelf_life_unit_enum",
        "items",
        "shelf_life_unit IS NULL OR shelf_life_unit IN ('DAY','WEEK','MONTH','YEAR')",
    )

    # has_shelf_life=false 时，不允许携带参数
    op.create_check_constraint(
        "ck_items_shelf_life_params_only_when_enabled",
        "items",
        "has_shelf_life = true OR (shelf_life_value IS NULL AND shelf_life_unit IS NULL)",
    )


def downgrade() -> None:
    # 先删约束
    op.drop_constraint("ck_items_shelf_life_params_only_when_enabled", "items", type_="check")
    op.drop_constraint("ck_items_shelf_life_unit_enum", "items", type_="check")
    op.drop_constraint("ck_items_shelf_life_value_pos", "items", type_="check")
    op.drop_constraint("ck_items_shelf_life_pair", "items", type_="check")

    # 加回列
    op.add_column(
        "items",
        sa.Column("shelf_life_days", sa.Integer(), nullable=True),
    )
    op.add_column(
        "items",
        sa.Column("qty_available", sa.Integer(), nullable=False, server_default="0"),
    )
