"""shipping_providers: drop external_outlet_code

Revision ID: a1108cfc2d66
Revises: 913f9087f201
Create Date: 2026-03-05 17:43:09.562079

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1108cfc2d66"
down_revision: Union[str, Sequence[str], None] = "913f9087f201"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 63b09d1eb510_shipping_providers_add_external_outlet_.py created:
    #   - column: shipping_providers.external_outlet_code
    #   - index : ix_shipping_providers_external_outlet_code
    #
    # Drop index first (safe if missing), then drop column.
    op.execute("DROP INDEX IF EXISTS ix_shipping_providers_external_outlet_code;")
    op.execute("ALTER TABLE shipping_providers DROP COLUMN IF EXISTS external_outlet_code;")


def downgrade() -> None:
    # Restore column + index to match prior behavior.
    op.execute("ALTER TABLE shipping_providers ADD COLUMN IF NOT EXISTS external_outlet_code VARCHAR(64);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_shipping_providers_external_outlet_code "
        "ON shipping_providers (external_outlet_code);"
    )
