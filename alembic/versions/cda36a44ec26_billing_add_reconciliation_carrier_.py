"""billing: add reconciliation carrier_status index

Revision ID: cda36a44ec26
Revises: 5c046a0c6332
Create Date: 2026-03-18 13:38:39.290902
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'cda36a44ec26'
down_revision: Union[str, Sequence[str], None] = '5c046a0c6332'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_index(
        "ix_shipping_record_reconciliations_carrier_status",
        "shipping_record_reconciliations",
        ["carrier_code", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_shipping_record_reconciliations_carrier_status",
        table_name="shipping_record_reconciliations",
    )
