"""wms_outbound_add_item_sku_snapshot_to_manual_doc_and_event_lines

Revision ID: d75f3fa5b346
Revises: 420e8062f56c
Create Date: 2026-04-20 14:41:00.015820

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d75f3fa5b346"
down_revision: Union[str, Sequence[str], None] = "420e8062f56c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "manual_outbound_lines",
        sa.Column("item_sku_snapshot", sa.Text(), nullable=True),
    )
    op.add_column(
        "outbound_event_lines",
        sa.Column("item_sku_snapshot", sa.String(length=64), nullable=True),
    )

    op.execute(
        """
        UPDATE manual_outbound_lines AS l
        SET item_sku_snapshot = i.sku
        FROM items AS i
        WHERE i.id = l.item_id
          AND l.item_sku_snapshot IS NULL
        """
    )

    op.execute(
        """
        UPDATE outbound_event_lines AS l
        SET item_sku_snapshot = i.sku
        FROM items AS i
        WHERE i.id = l.item_id
          AND l.item_sku_snapshot IS NULL
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("outbound_event_lines", "item_sku_snapshot")
    op.drop_column("manual_outbound_lines", "item_sku_snapshot")
