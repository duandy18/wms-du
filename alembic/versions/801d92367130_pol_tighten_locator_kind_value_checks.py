"""pol tighten locator_kind/value checks

Phase N+4 hardening:
- Add CHECK constraints to prevent blank locator fields
- Constrain locator_kind to allowed values when present
- Keep columns nullable for backward compatibility (no NOT NULL here)

Revision ID: 801d92367130
Revises: fec70b0a3640
Create Date: 2026-02-10 11:52:00.523142
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "801d92367130"
down_revision: Union[str, Sequence[str], None] = "fec70b0a3640"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Disallow blank strings (still allow NULL)
    op.execute(
        """
        ALTER TABLE platform_order_lines
        ADD CONSTRAINT ck_pol_locator_kind_not_blank
        CHECK (locator_kind IS NULL OR btrim(locator_kind) <> '');
        """
    )
    op.execute(
        """
        ALTER TABLE platform_order_lines
        ADD CONSTRAINT ck_pol_locator_value_not_blank
        CHECK (locator_value IS NULL OR btrim(locator_value) <> '');
        """
    )

    # Constrain locator_kind when present
    op.execute(
        """
        ALTER TABLE platform_order_lines
        ADD CONSTRAINT ck_pol_locator_kind_allowed
        CHECK (locator_kind IS NULL OR locator_kind IN ('FILLED_CODE', 'LINE_NO'));
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE platform_order_lines DROP CONSTRAINT IF EXISTS ck_pol_locator_kind_allowed;"
    )
    op.execute(
        "ALTER TABLE platform_order_lines DROP CONSTRAINT IF EXISTS ck_pol_locator_value_not_blank;"
    )
    op.execute(
        "ALTER TABLE platform_order_lines DROP CONSTRAINT IF EXISTS ck_pol_locator_kind_not_blank;"
    )
