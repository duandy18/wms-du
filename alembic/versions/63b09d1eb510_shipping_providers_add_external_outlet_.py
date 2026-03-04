"""shipping_providers: add external_outlet_code

Revision ID: 63b09d1eb510
Revises: 328e9ca43399
Create Date: 2026-03-03 17:59:16.675193
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "63b09d1eb510"
down_revision: Union[str, Sequence[str], None] = "328e9ca43399"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE shipping_providers
        ADD COLUMN external_outlet_code VARCHAR(64);
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_shipping_providers_external_outlet_code
        ON shipping_providers (external_outlet_code);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_shipping_providers_external_outlet_code;
        """
    )
    op.execute(
        """
        ALTER TABLE shipping_providers
        DROP COLUMN IF EXISTS external_outlet_code;
        """
    )
