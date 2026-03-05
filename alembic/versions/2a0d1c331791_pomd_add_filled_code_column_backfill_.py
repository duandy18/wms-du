"""pomd add filled_code column (backfill from platform_sku_id)

Phase N+3 / Step 1:
- Evidence table: platform_order_manual_decisions
- Add column: filled_code
- Backfill: filled_code <- platform_sku_id
- Keep legacy column for now (no drop here)

Revision ID: 2a0d1c331791
Revises: 0c45c147d9c8
Create Date: 2026-02-10 11:10:54.047542
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2a0d1c331791"
down_revision: Union[str, Sequence[str], None] = "0c45c147d9c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) add column (nullable; semantics unchanged)
    op.add_column(
        "platform_order_manual_decisions",
        sa.Column("filled_code", sa.Text(), nullable=True),
    )

    # 2) backfill history data: filled_code <- platform_sku_id
    #    Do NOT trim / normalize to avoid behavior changes.
    op.execute(
        sa.text(
            """
            UPDATE platform_order_manual_decisions
               SET filled_code = platform_sku_id
             WHERE platform_sku_id IS NOT NULL
               AND (filled_code IS NULL OR filled_code = '')
            """
        )
    )


def downgrade() -> None:
    # Rollback Step 1: simply drop the new column.
    op.drop_column("platform_order_manual_decisions", "filled_code")
