"""zones: allow segment_template_id nullable again

Revision ID: 52d1f9ef04c2
Revises: a76f7731b755
Create Date: 2026-01-29 14:25:05.956031

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "52d1f9ef04c2"
down_revision: Union[str, Sequence[str], None] = "a76f7731b755"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ✅ zones：允许 segment_template_id 为空（模板绑定迁移到二维工作台）
    op.alter_column(
        "shipping_provider_zones",
        "segment_template_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # ⚠️ 回滚到 NOT NULL 前，先清理仍为 NULL 的 zones，避免直接失败
    op.execute("DELETE FROM shipping_provider_zones WHERE segment_template_id IS NULL;")
    op.alter_column(
        "shipping_provider_zones",
        "segment_template_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
