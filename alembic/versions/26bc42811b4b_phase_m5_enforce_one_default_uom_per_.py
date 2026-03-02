"""phase m5: enforce one default uom per item

Revision ID: 26bc42811b4b
Revises: 4963d3727cc0
Create Date: 2026-03-01 16:25:00.794482

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "26bc42811b4b"
down_revision: Union[str, Sequence[str], None] = "4963d3727cc0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase M-5: unit_governance 二阶段
    - 强制每个 item 的默认单位唯一：
      * is_purchase_default
      * is_inbound_default
      * is_outbound_default

    采用 partial unique index（仅对 true 行生效）：
      unique(item_id) WHERE is_purchase_default = true
      unique(item_id) WHERE is_inbound_default  = true
      unique(item_id) WHERE is_outbound_default = true
    """
    op.create_index(
        "uq_item_uoms_one_purchase_default_per_item",
        "item_uoms",
        ["item_id"],
        unique=True,
        postgresql_where=sa.text("is_purchase_default = true"),
    )
    op.create_index(
        "uq_item_uoms_one_inbound_default_per_item",
        "item_uoms",
        ["item_id"],
        unique=True,
        postgresql_where=sa.text("is_inbound_default = true"),
    )
    op.create_index(
        "uq_item_uoms_one_outbound_default_per_item",
        "item_uoms",
        ["item_id"],
        unique=True,
        postgresql_where=sa.text("is_outbound_default = true"),
    )


def downgrade() -> None:
    op.drop_index("uq_item_uoms_one_outbound_default_per_item", table_name="item_uoms")
    op.drop_index("uq_item_uoms_one_inbound_default_per_item", table_name="item_uoms")
    op.drop_index("uq_item_uoms_one_purchase_default_per_item", table_name="item_uoms")
