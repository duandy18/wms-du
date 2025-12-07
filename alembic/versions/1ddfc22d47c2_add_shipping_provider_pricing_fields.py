"""add shipping provider pricing fields

Revision ID: 1ddfc22d47c2
Revises: 11dc33423ea3
Create Date: 2025-12-04 07:46:17.427432
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1ddfc22d47c2'
down_revision: Union[str, Sequence[str], None] = '11dc33423ea3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add priority / pricing_model / region_rules."""

    # priority：排序优先级（默认 100）
    op.add_column(
        "shipping_providers",
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default="100",
        ),
    )

    # pricing_model：计费模型 JSON
    op.add_column(
        "shipping_providers",
        sa.Column(
            "pricing_model",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # region_rules：区域定价覆盖 JSON
    op.add_column(
        "shipping_providers",
        sa.Column(
            "region_rules",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema: drop added fields."""
    op.drop_column("shipping_providers", "region_rules")
    op.drop_column("shipping_providers", "pricing_model")
    op.drop_column("shipping_providers", "priority")
