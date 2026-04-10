# alembic/versions/5542b7decf4b_add_net_weight_kg_to_item_uoms.py
"""add net_weight_kg to item_uoms

Revision ID: 5542b7decf4b
Revises: 1ebda503789f
Create Date: 2026-04-10 12:02:32.038483

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5542b7decf4b"
down_revision: Union[str, Sequence[str], None] = "1ebda503789f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add net_weight_kg column to item_uoms."""
    op.add_column(
        "item_uoms",
        sa.Column(
            "net_weight_kg",
            sa.Numeric(10, 3),
            nullable=True,
            comment="净重（kg）。基础包装为真相源；非基础包装默认可按 ratio_to_base 推导；不含包材。",
        ),
    )


def downgrade() -> None:
    """Drop net_weight_kg column from item_uoms."""
    op.drop_column("item_uoms", "net_weight_kg")
