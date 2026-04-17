"""procurement_purchase_order_lines_add_uom_name_snapshot

Revision ID: 4fb9df42573f
Revises: 3c7600f922bd
Create Date: 2026-04-17 13:33:25.898328

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4fb9df42573f'
down_revision: Union[str, Sequence[str], None] = '3c7600f922bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "purchase_order_lines",
        sa.Column("purchase_uom_name_snapshot", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        UPDATE purchase_order_lines pol
        SET purchase_uom_name_snapshot = COALESCE(iu.display_name, iu.uom)
        FROM item_uoms iu
        WHERE iu.id = pol.purchase_uom_id_snapshot
        """
    )
    op.alter_column(
        "purchase_order_lines",
        "purchase_uom_name_snapshot",
        existing_type=sa.String(length=64),
        nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("purchase_order_lines", "purchase_uom_name_snapshot")
