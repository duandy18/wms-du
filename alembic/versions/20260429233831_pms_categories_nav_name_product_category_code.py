"""Rename PMS categories navigation label.

Revision ID: 20260429233831
Revises: e4b8c31f7a2d
Create Date: 2026-04-29

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260429233831"
down_revision: Union[str, Sequence[str], None] = "e4b8c31f7a2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename pms.categories sidebar label to match the frontend page."""
    op.execute(
        """
        UPDATE page_registry
           SET name = '商品分类编码'
         WHERE code = 'pms.categories'
           AND name = '内部分类'
        """
    )


def downgrade() -> None:
    """Restore previous pms.categories sidebar label."""
    op.execute(
        """
        UPDATE page_registry
           SET name = '内部分类'
         WHERE code = 'pms.categories'
           AND name = '商品分类编码'
        """
    )
