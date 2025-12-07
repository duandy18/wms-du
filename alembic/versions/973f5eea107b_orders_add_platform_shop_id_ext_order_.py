"""orders: add platform/shop_id/ext_order_no/status/buyer/amount/extras + uq (strict)

Revision ID: 973f5eea107b
Revises: 3a707254e479
Create Date: 2025-11-07 16:57:37.127864
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "973f5eea107b"
down_revision: Union[str, Sequence[str], None] = "3a707254e479"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UQ = "uq_orders_platform_shop_ext"


def _has_column(bind, table: str, col: str) -> bool:
    sql = sa.text("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:t AND column_name=:c
        LIMIT 1
    """)
    return bind.execute(sql, {"t": table, "c": col}).first() is not None


def _has_constraint(bind, table: str, conname: str) -> bool:
    sql = sa.text("""
        SELECT 1 FROM pg_constraint
        WHERE conname=:n AND conrelid=('public.'||:t)::regclass
        LIMIT 1
    """)
    return bind.execute(sql, {"n": conname, "t": table}).first() is not None


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 严格补列（IF NOT EXISTS）
    bind.execute(sa.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS platform      VARCHAR(32)"))
    bind.execute(sa.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS shop_id       VARCHAR(128)"))
    bind.execute(sa.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS ext_order_no  VARCHAR(128)"))

    bind.execute(sa.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS status        VARCHAR(32)"))
    bind.execute(sa.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS buyer_name    VARCHAR(255)"))
    bind.execute(sa.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS buyer_phone   VARCHAR(64)"))

    bind.execute(sa.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_amount  NUMERIC(12,2)"))
    bind.execute(sa.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS pay_amount    NUMERIC(12,2)"))

    bind.execute(sa.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS extras        JSONB"))

    # 2) 回填（老数据安全收敛）
    if _has_column(bind, "orders", "order_no"):
        bind.execute(sa.text("UPDATE orders SET ext_order_no = COALESCE(ext_order_no, order_no)"))

    bind.execute(
        sa.text("UPDATE orders SET ext_order_no = COALESCE(ext_order_no, 'LEGACY-'||id::text)")
    )
    bind.execute(
        sa.text(
            "UPDATE orders SET platform = COALESCE(platform, 'LEGACY'), shop_id = COALESCE(shop_id, 'NO-STORE')"
        )
    )
    bind.execute(sa.text("UPDATE orders SET status = COALESCE(status, 'CREATED')"))
    bind.execute(
        sa.text(
            "UPDATE orders SET order_amount = COALESCE(order_amount, 0.00), pay_amount = COALESCE(pay_amount, 0.00)"
        )
    )
    bind.execute(sa.text("UPDATE orders SET extras = COALESCE(extras, '{}'::jsonb)"))

    # 3) 约束与默认（现在再加，不会被 NULL 卡住）
    bind.execute(sa.text("ALTER TABLE orders ALTER COLUMN platform     SET NOT NULL"))
    bind.execute(sa.text("ALTER TABLE orders ALTER COLUMN shop_id      SET NOT NULL"))
    bind.execute(sa.text("ALTER TABLE orders ALTER COLUMN ext_order_no SET NOT NULL"))
    bind.execute(sa.text("ALTER TABLE orders ALTER COLUMN status       SET NOT NULL"))
    bind.execute(sa.text("ALTER TABLE orders ALTER COLUMN order_amount SET NOT NULL"))
    bind.execute(sa.text("ALTER TABLE orders ALTER COLUMN pay_amount   SET NOT NULL"))
    bind.execute(sa.text("ALTER TABLE orders ALTER COLUMN extras       SET NOT NULL"))

    bind.execute(sa.text("ALTER TABLE orders ALTER COLUMN status       SET DEFAULT 'CREATED'"))
    bind.execute(sa.text("ALTER TABLE orders ALTER COLUMN order_amount SET DEFAULT 0.00"))
    bind.execute(sa.text("ALTER TABLE orders ALTER COLUMN pay_amount   SET DEFAULT 0.00"))
    bind.execute(sa.text("ALTER TABLE orders ALTER COLUMN extras       SET DEFAULT '{}'::jsonb"))

    # 4) 幂等唯一键：(platform, shop_id, ext_order_no)
    if not _has_constraint(bind, "orders", _UQ):
        bind.execute(
            sa.text(
                f"ALTER TABLE orders ADD CONSTRAINT {_UQ} UNIQUE (platform, shop_id, ext_order_no)"
            )
        )

    # 5) 辅助索引（按业务号 + 时间回放；存在就跳过）
    if _has_column(bind, "orders", "created_at"):
        bind.execute(
            sa.text("""
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname='public' AND c.relname='ix_orders_no_created_at'
              ) THEN
                CREATE INDEX ix_orders_no_created_at ON orders (ext_order_no, created_at);
              END IF;
            END $$;
        """)
        )


def downgrade() -> None:
    bind = op.get_bind()

    bind.execute(sa.text("DROP INDEX IF EXISTS ix_orders_no_created_at"))
    bind.execute(
        sa.text(
            "ALTER TABLE IF EXISTS orders DROP CONSTRAINT IF EXISTS uq_orders_platform_shop_ext"
        )
    )

    bind.execute(sa.text("ALTER TABLE IF EXISTS orders ALTER COLUMN extras       DROP DEFAULT"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders ALTER COLUMN pay_amount   DROP DEFAULT"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders ALTER COLUMN order_amount DROP DEFAULT"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders ALTER COLUMN status       DROP DEFAULT"))

    bind.execute(sa.text("ALTER TABLE IF EXISTS orders DROP COLUMN IF EXISTS extras"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders DROP COLUMN IF EXISTS pay_amount"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders DROP COLUMN IF EXISTS order_amount"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders DROP COLUMN IF EXISTS buyer_phone"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders DROP COLUMN IF EXISTS buyer_name"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders DROP COLUMN IF EXISTS status"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders DROP COLUMN IF EXISTS ext_order_no"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders DROP COLUMN IF EXISTS shop_id"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders DROP COLUMN IF EXISTS platform"))
