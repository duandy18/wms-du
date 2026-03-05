"""drop ruleset_key from shipping_provider_pricing_schemes

Revision ID: 2aff8011003f
Revises: 72ae00a785a3
Create Date: 2026-01-28 14:14:28.230344

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2aff8011003f"
down_revision: Union[str, Sequence[str], None] = "72ae00a785a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("shipping_provider_pricing_schemes", "ruleset_key")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "shipping_provider_pricing_schemes",
        sa.Column(
            "ruleset_key",
            sa.String(length=64),
            nullable=False,
            server_default="segments_standard",
        ),
    )
    # 清掉 server_default，保持与 ORM 行为一致
    op.alter_column("shipping_provider_pricing_schemes", "ruleset_key", server_default=None)
