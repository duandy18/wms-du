"""drop legacy supplier contact columns

Revision ID: 2da444804c8f
Revises: 48c2179fbd19
Create Date: 2025-12-13 14:00:53.168353

目的：
- suppliers 表删除遗留字段：contact_name / phone / email / wechat
- 供应商联系人以后只认 supplier_contacts
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2da444804c8f"
down_revision: Union[str, Sequence[str], None] = "48c2179fbd19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ⚠️ 注意：该迁移会永久删除旧列数据。
    # 执行前请确保旧列数据已迁移到 supplier_contacts（或确认旧列为空）。
    op.drop_column("suppliers", "contact_name")
    op.drop_column("suppliers", "phone")
    op.drop_column("suppliers", "email")
    op.drop_column("suppliers", "wechat")


def downgrade() -> None:
    # 回滚：仅恢复列结构（不恢复被删除的数据）
    op.add_column("suppliers", sa.Column("contact_name", sa.String(length=100), nullable=True))
    op.add_column("suppliers", sa.Column("phone", sa.String(length=50), nullable=True))
    op.add_column("suppliers", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("suppliers", sa.Column("wechat", sa.String(length=64), nullable=True))
