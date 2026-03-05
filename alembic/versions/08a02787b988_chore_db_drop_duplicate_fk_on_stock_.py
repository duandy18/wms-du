"""chore(db): drop duplicate FK on stock_ledger.item_id

Revision ID: 08a02787b988
Revises: 4259e5deb13b
Create Date: 2026-02-24 17:16:59.168941

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "08a02787b988"
down_revision: Union[str, Sequence[str], None] = "4259e5deb13b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Remove duplicate foreign key on stock_ledger.item_id.

    Current state before this migration:
    - fk_stock_ledger_item        (ON DELETE SET NULL)
    - fk_stock_ledger_item_id     (ON DELETE RESTRICT)

    We keep the RESTRICT one and drop the SET NULL one.
    """

    op.execute(
        """
        ALTER TABLE stock_ledger
        DROP CONSTRAINT IF EXISTS fk_stock_ledger_item;
        """
    )


def downgrade() -> None:
    """
    Restore the previously dropped foreign key (ON DELETE SET NULL).

    This keeps migration reversible, even though
    the duplicate FK is considered legacy noise.
    """

    op.execute(
        """
        ALTER TABLE stock_ledger
        ADD CONSTRAINT fk_stock_ledger_item
        FOREIGN KEY (item_id)
        REFERENCES items(id)
        ON DELETE SET NULL;
        """
    )
