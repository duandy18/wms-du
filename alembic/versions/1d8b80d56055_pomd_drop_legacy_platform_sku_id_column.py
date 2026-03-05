"""pomd drop legacy platform_sku_id column

Phase N+3 / Step 4:
- Evidence table: platform_order_manual_decisions
- Drop legacy column: platform_sku_id
- Keep filled_code as the only semantic column

Revision ID: 1d8b80d56055
Revises: 2a0d1c331791
Create Date: 2026-02-10 11:19:31.354065
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1d8b80d56055"
down_revision: Union[str, Sequence[str], None] = "2a0d1c331791"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Phase N+3 final step:
    # drop legacy column, no behavior change (column already unused)
    op.drop_column("platform_order_manual_decisions", "platform_sku_id")


def downgrade() -> None:
    # Rollback: re-add legacy column and backfill from filled_code
    op.add_column(
        "platform_order_manual_decisions",
        sa.Column("platform_sku_id", sa.Text(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE platform_order_manual_decisions
               SET platform_sku_id = filled_code
             WHERE filled_code IS NOT NULL
               AND (platform_sku_id IS NULL OR platform_sku_id = '')
            """
        )
    )
