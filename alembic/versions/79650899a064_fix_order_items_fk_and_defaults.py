"""fix_order_items_fk_and_defaults

Revision ID: 79650899a064
Revises: 8cb81054e8ee
Create Date: 2026-02-07 16:03:56.072869
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "79650899a064"
down_revision: Union[str, Sequence[str], None] = "8cb81054e8ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    1) 删除矛盾外键：
       - fk_order_items_item_id_items: ON DELETE SET NULL
       - 但 order_items.item_id 是 NOT NULL，因此这条 FK 永远无法正确工作
    2) 给 shipped_qty/returned_qty 补 server default 0，避免后续插入踩 NOT NULL
    """
    op.execute("ALTER TABLE order_items DROP CONSTRAINT IF EXISTS fk_order_items_item_id_items")
    op.execute("ALTER TABLE order_items ALTER COLUMN shipped_qty SET DEFAULT 0")
    op.execute("ALTER TABLE order_items ALTER COLUMN returned_qty SET DEFAULT 0")


def downgrade() -> None:
    """
    可逆，但不推荐回滚到矛盾状态；这里仅保证形式可 downgrade。
    """
    op.execute("ALTER TABLE order_items ALTER COLUMN shipped_qty DROP DEFAULT")
    op.execute("ALTER TABLE order_items ALTER COLUMN returned_qty DROP DEFAULT")
    op.execute(
        """
        ALTER TABLE order_items
        ADD CONSTRAINT fk_order_items_item_id_items
        FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE SET NULL
        """
    )
