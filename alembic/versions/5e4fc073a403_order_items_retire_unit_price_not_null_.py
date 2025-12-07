"""order_items: retire unit_price NOT NULL, standardize price

Revision ID: 5e4fc073a403
Revises: 8fdf6551cc08
Create Date: 2025-11-07 17:21:14.361710
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "5e4fc073a403"
down_revision: Union[str, Sequence[str], None] = "8fdf6551cc08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, col: str) -> bool:
    row = bind.execute(
        sa.text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t AND column_name=:c
            LIMIT 1
        """),
        {"t": table, "c": col},
    ).first()
    return row is not None


def _col_is_not_null(bind, table: str, col: str) -> bool:
    row = bind.execute(
        sa.text("""
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t AND column_name=:c
        """),
        {"t": table, "c": col},
    ).first()
    return bool(row and row[0] == "NO")


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 确保新口径列 price 存在且可用（NOT NULL + DEFAULT 0.00）
    bind.execute(sa.text("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS price NUMERIC(12,2)"))
    bind.execute(sa.text("UPDATE order_items SET price=0.00 WHERE price IS NULL"))
    bind.execute(sa.text("ALTER TABLE order_items ALTER COLUMN price SET DEFAULT 0.00"))
    bind.execute(sa.text("ALTER TABLE order_items ALTER COLUMN price SET NOT NULL"))

    # 2) 如有历史列 unit_price，先同步到 price（不覆盖已有的 price）
    if _has_column(bind, "order_items", "unit_price"):
        bind.execute(sa.text("UPDATE order_items SET price = COALESCE(price, unit_price)"))
        # 将 unit_price 退役为可空（避免插入时报 NOT NULL）
        if _col_is_not_null(bind, "order_items", "unit_price"):
            bind.execute(sa.text("ALTER TABLE order_items ALTER COLUMN unit_price DROP NOT NULL"))
        # 如确认无用，后续可在新迁移中 DROP COLUMN unit_price

    # 3) 其它金额列兜底（严格对齐合同）
    bind.execute(sa.text("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS discount NUMERIC(12,2)"))
    bind.execute(sa.text("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS amount   NUMERIC(12,2)"))
    bind.execute(sa.text("UPDATE order_items SET discount=0.00 WHERE discount IS NULL"))
    bind.execute(sa.text("UPDATE order_items SET amount=0.00   WHERE amount   IS NULL"))
    bind.execute(sa.text("ALTER TABLE order_items ALTER COLUMN discount SET DEFAULT 0.00"))
    bind.execute(sa.text("ALTER TABLE order_items ALTER COLUMN amount   SET DEFAULT 0.00"))
    bind.execute(sa.text("ALTER TABLE order_items ALTER COLUMN discount SET NOT NULL"))
    bind.execute(sa.text("ALTER TABLE order_items ALTER COLUMN amount   SET NOT NULL"))


def downgrade() -> None:
    bind = op.get_bind()
    # 回滚策略：仅撤销我们新增/修改的强制属性，保留列
    bind.execute(sa.text("ALTER TABLE IF EXISTS order_items ALTER COLUMN price DROP NOT NULL"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS order_items ALTER COLUMN price DROP DEFAULT"))
    # 若需恢复 unit_price 为 NOT NULL（仅在确认无 NULL 时），可在后续按需另起迁移处理
