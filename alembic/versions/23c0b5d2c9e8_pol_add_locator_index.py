"""pol add locator index

Phase N+4 performance hardening:
- Add composite index to support locator-based lookups
- Index aligns with confirm/replay/manual-decision query patterns

Revision ID: 23c0b5d2c9e8
Revises: 801d92367130
Create Date: 2026-02-10 11:56:03.729994
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "23c0b5d2c9e8"
down_revision: Union[str, Sequence[str], None] = "801d92367130"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite locator index:
    # (platform, store_id, ext_order_no, locator_kind, locator_value)
    #
    # Rationale:
    # - platform + store_id + ext_order_no scopes an order
    # - locator_kind/value enables fast semantic line lookup
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pol_locator
        ON platform_order_lines
        (platform, store_id, ext_order_no, locator_kind, locator_value);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_pol_locator;")
