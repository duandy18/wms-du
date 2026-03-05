"""scope phase3: orders add scope + uq include scope

Revision ID: 1ff62e046f8e
Revises: 2d119fb173a7
Create Date: 2026-02-13 14:44:38.191451

Phase 3 起点：

- 新增 orders.scope (biz_scope)
- 将 uq_orders_platform_shop_ext 升级为 UNIQUE(scope, platform, shop_id, ext_order_no)
- 新增 ix_orders_scope_platform_shop 辅助索引
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1ff62e046f8e"
down_revision: Union[str, Sequence[str], None] = "2d119fb173a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------- small helpers ----------
def _col_exists(conn, table: str, col: str) -> bool:
    res = conn.exec_driver_sql(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        LIMIT 1
        """,
        (table, col),
    ).first()
    return res is not None


def _constraint_exists(conn, name: str) -> bool:
    res = conn.exec_driver_sql(
        "SELECT 1 FROM pg_constraint WHERE conname=%s LIMIT 1",
        (name,),
    ).first()
    return res is not None


def _index_exists(conn, name: str) -> bool:
    res = conn.exec_driver_sql(
        """
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind='i' AND c.relname=%s AND n.nspname='public'
        LIMIT 1
        """,
        (name,),
    ).first()
    return res is not None


# ---------------- upgrade ----------------
def upgrade() -> None:
    conn = op.get_bind()

    # 1️⃣ 新增 scope 列（biz_scope 类型已在库存阶段创建）
    if not _col_exists(conn, "orders", "scope"):
        op.execute("ALTER TABLE orders ADD COLUMN scope biz_scope")
        op.execute("ALTER TABLE orders ALTER COLUMN scope SET DEFAULT 'PROD'")

    # 回填历史数据
    op.execute("UPDATE orders SET scope='PROD' WHERE scope IS NULL")

    # 强制非空
    op.execute("ALTER TABLE orders ALTER COLUMN scope SET NOT NULL")
    op.execute("ALTER TABLE orders ALTER COLUMN scope DROP DEFAULT")
    op.execute("COMMENT ON COLUMN orders.scope IS '订单 scope（PROD/DRILL）。DRILL 与 PROD 订单宇宙隔离。'")

    # 2️⃣ 升级唯一约束：纳入 scope
    if _constraint_exists(conn, "uq_orders_platform_shop_ext"):
        op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS uq_orders_platform_shop_ext")

    op.execute(
        """
        ALTER TABLE orders
        ADD CONSTRAINT uq_orders_platform_shop_ext
        UNIQUE (scope, platform, shop_id, ext_order_no)
        """
    )

    # 3️⃣ 辅助索引（列表/统计常用）
    if not _index_exists(conn, "ix_orders_scope_platform_shop"):
        op.execute(
            "CREATE INDEX ix_orders_scope_platform_shop "
            "ON orders (scope, platform, shop_id)"
        )


# ---------------- downgrade ----------------
def downgrade() -> None:
    conn = op.get_bind()

    # 删除辅助索引
    if _index_exists(conn, "ix_orders_scope_platform_shop"):
        op.execute("DROP INDEX IF EXISTS ix_orders_scope_platform_shop")

    # 恢复旧唯一约束
    if _constraint_exists(conn, "uq_orders_platform_shop_ext"):
        op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS uq_orders_platform_shop_ext")

    op.execute(
        """
        ALTER TABLE orders
        ADD CONSTRAINT uq_orders_platform_shop_ext
        UNIQUE (platform, shop_id, ext_order_no)
        """
    )

    # 删除 scope 列
    if _col_exists(conn, "orders", "scope"):
        op.execute("ALTER TABLE orders DROP COLUMN scope")
