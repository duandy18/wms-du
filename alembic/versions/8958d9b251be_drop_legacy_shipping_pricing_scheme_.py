"""drop legacy shipping pricing scheme tables

Revision ID: 8958d9b251be
Revises: 5ec3e70b5ea9
Create Date: 2026-03-20 23:39:07.971328
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8958d9b251be'
down_revision: Union[str, Sequence[str], None] = '5ec3e70b5ea9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """彻底删除旧 scheme 体系（表 + 触发器函数）"""

    # ===== 1) 先删 trigger（依赖函数）=====
    op.execute("DROP TRIGGER IF EXISTS trg_sp_surcharge_config_on_city ON shipping_provider_surcharge_config_cities")
    op.execute("DROP TRIGGER IF EXISTS trg_sp_surcharge_config_on_config ON shipping_provider_surcharge_configs")

    # ===== 2) 再删 function =====
    op.execute("DROP FUNCTION IF EXISTS trg_validate_sp_surcharge_config_on_city()")
    op.execute("DROP FUNCTION IF EXISTS trg_validate_sp_surcharge_config_on_config()")

    # ===== 3) 按依赖顺序 drop 表 =====
    op.drop_table("shipping_provider_surcharge_config_cities")
    op.drop_table("shipping_provider_surcharge_configs")
    op.drop_table("shipping_provider_pricing_matrix")
    op.drop_table("shipping_provider_destination_group_members")
    op.drop_table("shipping_provider_destination_groups")
    op.drop_table("shipping_provider_pricing_scheme_module_ranges")
    op.drop_table("shipping_provider_pricing_schemes")


def downgrade() -> None:
    """不支持回滚（避免引入旧体系）"""
    raise Exception("Downgrade not supported for dropping legacy pricing scheme tables")
