"""reservations: drop NOT NULL on qty + default 0

Revision ID: 3d473566713c
Revises: 21fcb6145817
Create Date: 2025-11-08 07:04:39.795169
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "3d473566713c"
down_revision: Union[str, Sequence[str], None] = "21fcb6145817"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # 仅在存在 qty 列时执行
    exists = bind.execute(
        sa.text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name='reservations'
              AND column_name='qty'
            LIMIT 1
        """)
    ).first()
    if not exists:
        return

    # 回填 null -> 0
    bind.execute(sa.text("UPDATE reservations SET qty = COALESCE(qty, 0)"))
    # 删除 NOT NULL 约束
    bind.execute(sa.text("ALTER TABLE reservations ALTER COLUMN qty DROP NOT NULL"))
    # 设置默认值 0
    bind.execute(sa.text("ALTER TABLE reservations ALTER COLUMN qty SET DEFAULT 0"))


def downgrade() -> None:
    bind = op.get_bind()
    # 仅当 qty 存在时移除默认值（不恢复 NOT NULL）
    exists = bind.execute(
        sa.text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name='reservations'
              AND column_name='qty'
            LIMIT 1
        """)
    ).first()
    if not exists:
        return
    bind.execute(sa.text("ALTER TABLE reservations ALTER COLUMN qty DROP DEFAULT"))
