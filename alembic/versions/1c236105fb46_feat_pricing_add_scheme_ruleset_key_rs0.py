"""feat(pricing): add scheme ruleset_key (RS0)

Revision ID: 1c236105fb46
Revises: a9c1b7827263
Create Date: 2026-01-27 18:10:17.685399

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1c236105fb46"
down_revision: Union[str, Sequence[str], None] = "a9c1b7827263"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ✅ RS0：计价规则族（ruleset_key）
    # 1) 先加列并给 server_default，确保历史行被一次性填充
    op.add_column(
        "shipping_provider_pricing_schemes",
        sa.Column(
            "ruleset_key",
            sa.String(length=64),
            nullable=False,
            server_default="segments_standard",
        ),
    )

    # 2) 推荐：撤掉 server_default，避免未来遗漏写入被 DB 默默兜底，导致口径漂移
    op.alter_column(
        "shipping_provider_pricing_schemes",
        "ruleset_key",
        server_default=None,
        existing_type=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("shipping_provider_pricing_schemes", "ruleset_key")
