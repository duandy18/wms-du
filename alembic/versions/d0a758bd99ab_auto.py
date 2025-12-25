"""drop_shipping_providers_legacy_contact_columns

Revision ID: d0a758bd99ab
Revises: f213ac3821b2
Create Date: 2025-12-13 17:04:14.030369
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d0a758bd99ab"
down_revision: Union[str, Sequence[str], None] = "f213ac3821b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    A 线收官：彻底消灭 Shipping Providers 的 legacy 单联系人列，避免事实双写入口。

    Drop columns:
      - shipping_providers.contact_name
      - shipping_providers.phone
      - shipping_providers.email
      - shipping_providers.wechat
    """
    op.drop_column("shipping_providers", "contact_name")
    op.drop_column("shipping_providers", "phone")
    op.drop_column("shipping_providers", "email")
    op.drop_column("shipping_providers", "wechat")


def downgrade() -> None:
    """
    回滚：加回 legacy 列（nullable），不做任何回填。
    """
    op.add_column(
        "shipping_providers",
        sa.Column("wechat", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "shipping_providers",
        sa.Column("email", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "shipping_providers",
        sa.Column("phone", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "shipping_providers",
        sa.Column("contact_name", sa.String(length=100), nullable=True),
    )
