"""pol add locator_kind/value (semantic locator for external use)

Phase N+4 / Step 1:
- platform_order_lines: add locator_kind, locator_value
- backfill from existing filled_code / line_no
- keep line_key as internal idempotency key (unchanged)

Revision ID: fec70b0a3640
Revises: 1d8b80d56055
Create Date: 2026-02-10 11:33:08.207118
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fec70b0a3640"
down_revision: Union[str, Sequence[str], None] = "1d8b80d56055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) add semantic locator columns (nullable for backward compatibility)
    op.add_column(
        "platform_order_lines",
        sa.Column("locator_kind", sa.Text(), nullable=True),
    )
    op.add_column(
        "platform_order_lines",
        sa.Column("locator_value", sa.Text(), nullable=True),
    )

    # 2) backfill existing rows:
    #    - prefer filled_code when present
    #    - fallback to line_no
    op.execute(
        sa.text(
            """
            UPDATE platform_order_lines
               SET locator_kind  = CASE
                                    WHEN filled_code IS NOT NULL AND btrim(filled_code) <> ''
                                      THEN 'FILLED_CODE'
                                    ELSE 'LINE_NO'
                                  END,
                   locator_value = CASE
                                    WHEN filled_code IS NOT NULL AND btrim(filled_code) <> ''
                                      THEN filled_code
                                    ELSE (line_no::text)
                                  END
             WHERE locator_kind IS NULL
                OR locator_kind = ''
            """
        )
    )


def downgrade() -> None:
    # Rollback: simply drop semantic locator columns
    op.drop_column("platform_order_lines", "locator_value")
    op.drop_column("platform_order_lines", "locator_kind")
