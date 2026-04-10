# alembic/versions/6994653cf477_backfill_base_uom_net_weight_kg_from_.py
"""backfill base uom net_weight_kg from items

Revision ID: 6994653cf477
Revises: 5542b7decf4b
Create Date: 2026-04-10 12:08:26.636116

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "6994653cf477"
down_revision: Union[str, Sequence[str], None] = "5542b7decf4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill base item_uoms.net_weight_kg from items.weight_kg."""
    op.execute(
        """
        UPDATE item_uoms AS u
           SET net_weight_kg = i.weight_kg
          FROM items AS i
         WHERE u.item_id = i.id
           AND u.is_base = true
           AND i.weight_kg IS NOT NULL
           AND u.net_weight_kg IS NULL
        """
    )


def downgrade() -> None:
    """Clear backfilled base item_uoms.net_weight_kg values."""
    op.execute(
        """
        UPDATE item_uoms AS u
           SET net_weight_kg = NULL
          FROM items AS i
         WHERE u.item_id = i.id
           AND u.is_base = true
           AND i.weight_kg IS NOT NULL
        """
    )
