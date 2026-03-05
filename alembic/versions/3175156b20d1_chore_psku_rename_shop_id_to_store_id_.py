"""chore(psku): rename shop_id to store_id in platform_sku tables

Revision ID: 3175156b20d1
Revises: 79650899a064
Create Date: 2026-02-07 16:10:50.168817
"""
from __future__ import annotations

from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3175156b20d1"
down_revision: Union[str, Sequence[str], None] = "79650899a064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    将 platform_sku_* 表中误名的 shop_id(int) 改为 store_id(int)
    语义不变，仅做命名澄清
    """
    op.execute(
        "ALTER TABLE platform_sku_bindings "
        "RENAME COLUMN shop_id TO store_id"
    )
    op.execute(
        "ALTER TABLE platform_sku_mirror "
        "RENAME COLUMN shop_id TO store_id"
    )


def downgrade() -> None:
    """
    回滚命名（不推荐，但保证可逆）
    """
    op.execute(
        "ALTER TABLE platform_sku_bindings "
        "RENAME COLUMN store_id TO shop_id"
    )
    op.execute(
        "ALTER TABLE platform_sku_mirror "
        "RENAME COLUMN store_id TO shop_id"
    )
