"""order_items: retire line_amount NOT NULL, standardize amount

Revision ID: 2082f8e1dad3
Revises: 5e4fc073a403
Create Date: 2025-11-07 17:26:38.327528
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "2082f8e1dad3"
down_revision: Union[str, Sequence[str], None] = "5e4fc073a403"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, col: str) -> bool:
    row = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t AND column_name=:c
            LIMIT 1
            """
        ),
        {"t": table, "c": col},
    ).first()
    return row is not None


def _col_is_not_null(bind, table: str, col: str) -> bool:
    row = bind.execute(
        sa.text(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t AND column_name=:c
            """
        ),
        {"t": table, "c": col},
    ).first()
    return bool(row and row[0] == "NO")


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 确保新口径列 amount 存在且可用（NOT NULL + DEFAULT 0.00）
    bind.execute(sa.text("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS amount NUMERIC(12,2)"))
    bind.execute(sa.text("UPDATE order_items SET amount=0.00 WHERE amount IS NULL"))
    bind.execute(sa.text("ALTER TABLE order_items ALTER COLUMN amount SET DEFAULT 0.00"))
    bind.execute(sa.text("ALTER TABLE order_items ALTER COLUMN amount SET NOT NULL"))

    # 2) 如有历史列 line_amount：同步到 amount（不覆盖已有 amount）
    if _has_column(bind, "order_items", "line_amount"):
        bind.execute(sa.text("UPDATE order_items SET amount = COALESCE(amount, line_amount)"))
        # 3) 将 line_amount 退役为可空，避免新插入时报 NOT NULL
        if _col_is_not_null(bind, "order_items", "line_amount"):
            bind.execute(sa.text("ALTER TABLE order_items ALTER COLUMN line_amount DROP NOT NULL"))
        # （可选）确认无用后，在后续迁移中 DROP COLUMN line_amount


def downgrade() -> None:
    bind = op.get_bind()
    # 回滚：仅撤销我们对 amount 的强制属性，保留列
    bind.execute(sa.text("ALTER TABLE IF EXISTS order_items ALTER COLUMN amount DROP NOT NULL"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS order_items ALTER COLUMN amount DROP DEFAULT"))
