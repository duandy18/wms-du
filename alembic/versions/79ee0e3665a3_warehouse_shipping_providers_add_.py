"""warehouse_shipping_providers_add_effective_from_and_disabled_at

Revision ID: 79ee0e3665a3
Revises: 0ed8bde1dd67
Create Date: 2026-03-23 13:42:22.984005

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79ee0e3665a3'
down_revision: Union[str, Sequence[str], None] = '0ed8bde1dd67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ✅ 新增：生效时间（允许 NULL，NULL 表示“立即生效 / 历史已生效”）
    op.add_column(
        "warehouse_shipping_providers",
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # ✅ 新增：停用时间（仅用于审计/展示，不参与运行判断）
    op.add_column(
        "warehouse_shipping_providers",
        sa.Column(
            "disabled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""

    # ⚠️ 回滚顺序：先删 disabled_at，再删 effective_from
    op.drop_column("warehouse_shipping_providers", "disabled_at")
    op.drop_column("warehouse_shipping_providers", "effective_from")
