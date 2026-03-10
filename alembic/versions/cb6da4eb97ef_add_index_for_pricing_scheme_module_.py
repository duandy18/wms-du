"""add index for pricing_scheme_module_ranges.scheme_id

Revision ID: cb6da4eb97ef
Revises: 49bacdd7e9b7
Create Date: 2026-03-10 09:10:26.648712
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cb6da4eb97ef"
down_revision: Union[str, Sequence[str], None] = "49bacdd7e9b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS
            ix_shipping_provider_pricing_scheme_module_ranges_scheme_id
            ON shipping_provider_pricing_scheme_module_ranges (scheme_id)
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS
            ix_shipping_provider_pricing_scheme_module_ranges_scheme_id
            """
        )
    )
