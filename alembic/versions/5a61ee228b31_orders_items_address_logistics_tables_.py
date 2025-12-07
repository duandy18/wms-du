"""orders+: items/address/logistics tables + expand orders (strict schema)

Revision ID: 5a61ee228b31
Revises: 7a9c9bfbf3af
Create Date: 2025-11-07 14:55:15.609041
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# --- Alembic identifiers ---
revision: str = "5a61ee228b31"
down_revision: Union[str, Sequence[str], None] = "7a9c9bfbf3af"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 常量
CHK_ORDERS_AMOUNT = "chk_orders_amount_nonneg"
IDX_ORDERS_NO_TIME = "ix_orders_no_created_at"
UQ_ORDER_ITEMS_ORD_SKU = "uq_order_items_ord_sku"
FK_ORDER_ITEMS_ITEM = "fk_order_items_item_id_items"
CHK_ORDER_ITEMS_QTY = "chk_order_items_qty_pos"
CHK_ORDER_ITEMS_AMT = "chk_order_items_amount_nonneg"
IDX_ORDLOG_ORD_TRK = "ix_order_logistics_ord_trk"


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table, schema="public")


def _has_constraint(bind, table: str, conname: str) -> bool:
    sql = sa.text("""
        SELECT 1
        FROM pg_constraint
        WHERE conname=:n AND conrelid=('public.'||:t)::regclass
        LIMIT 1
    """)
    return bind.execute(sql, {"n": conname, "t": table}).first() is not None


def _has_column(bind, table: str, col: str) -> bool:
    sql = sa.text("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:t AND column_name=:c
        LIMIT 1
    """)
    return bind.execute(sql, {"t": table, "c": col}).first() is not None


def upgrade() -> None:
    bind = op.get_bind()

    # -------------------- 扩展 orders（强约束） --------------------
    bind.execute(sa.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS buyer_name  VARCHAR(255)"))
    bind.execute(sa.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS buyer_phone VARCHAR(64)"))
    bind.execute(sa.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_amount NUMERIC(12,2)"))
    bind.execute(sa.text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS pay_amount   NUMERIC(12,2)"))
    bind.execute(sa.text("UPDATE orders SET order_amount=0.00 WHERE order_amount IS NULL"))
    bind.execute(sa.text("UPDATE orders SET pay_amount=0.00   WHERE pay_amount   IS NULL"))
    bind.execute(sa.text("ALTER TABLE orders ALTER COLUMN order_amount SET DEFAULT 0.00"))
    bind.execute(sa.text("ALTER TABLE orders ALTER COLUMN pay_amount   SET DEFAULT 0.00"))
    if not _has_constraint(bind, "orders", CHK_ORDERS_AMOUNT):
        bind.execute(
            sa.text(f"""
            ALTER TABLE orders
            ADD CONSTRAINT {CHK_ORDERS_AMOUNT}
            CHECK (order_amount >= 0 AND pay_amount >= 0)
        """)
        )
    # 业务号+时间索引（按你的口径，如使用 order_no 就改成 order_no）
    if not _has_column(bind, "orders", "ext_order_no"):
        bind.execute(
            sa.text(
                f"CREATE INDEX IF NOT EXISTS {IDX_ORDERS_NO_TIME} ON orders (order_no, created_at)"
            )
        )
    else:
        bind.execute(
            sa.text(
                f"CREATE INDEX IF NOT EXISTS {IDX_ORDERS_NO_TIME} ON orders (ext_order_no, created_at)"
            )
        )

    # -------------------- order_items（严格对齐标准结构） --------------------
    if not _has_table(bind, "order_items"):
        op.create_table(
            "order_items",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column(
                "order_id",
                sa.BigInteger(),
                sa.ForeignKey("orders.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("item_id", sa.Integer(), nullable=True),
            sa.Column("sku_id", sa.String(128), nullable=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("qty", sa.Integer(), nullable=False),
            sa.Column("price", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
            sa.Column(
                "discount", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")
            ),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        )
    else:
        # ☆ 表已存在：逐列硬补，确保标准结构
        for col, ddl in [
            ("order_id", "BIGINT"),
            ("item_id", "INTEGER"),
            ("sku_id", "VARCHAR(128)"),
            ("title", "VARCHAR(255)"),
            ("qty", "INTEGER"),
            ("price", "NUMERIC(12,2)"),
            ("discount", "NUMERIC(12,2)"),
            ("amount", "NUMERIC(12,2)"),
        ]:
            if not _has_column(bind, "order_items", col):
                bind.execute(sa.text(f"ALTER TABLE order_items ADD COLUMN {col} {ddl}"))
        # 数值列默认与非负初始化
        bind.execute(sa.text("UPDATE order_items SET price=0.00   WHERE price   IS NULL"))
        bind.execute(sa.text("UPDATE order_items SET discount=0.00 WHERE discount IS NULL"))
        bind.execute(sa.text("UPDATE order_items SET amount=0.00   WHERE amount   IS NULL"))
        bind.execute(sa.text("ALTER TABLE order_items ALTER COLUMN price   SET DEFAULT 0.00"))
        bind.execute(sa.text("ALTER TABLE order_items ALTER COLUMN discount SET DEFAULT 0.00"))
        bind.execute(sa.text("ALTER TABLE order_items ALTER COLUMN amount   SET DEFAULT 0.00"))

    # 约束：唯一 & 检查
    if not _has_constraint(bind, "order_items", UQ_ORDER_ITEMS_ORD_SKU):
        bind.execute(
            sa.text(f"""
            ALTER TABLE order_items
            ADD CONSTRAINT {UQ_ORDER_ITEMS_ORD_SKU} UNIQUE (order_id, sku_id)
        """)
        )
    if not _has_constraint(bind, "order_items", CHK_ORDER_ITEMS_QTY):
        bind.execute(
            sa.text(f"ALTER TABLE order_items ADD CONSTRAINT {CHK_ORDER_ITEMS_QTY} CHECK (qty > 0)")
        )
    if not _has_constraint(bind, "order_items", CHK_ORDER_ITEMS_AMT):
        bind.execute(
            sa.text(f"""
            ALTER TABLE order_items
            ADD CONSTRAINT {CHK_ORDER_ITEMS_AMT}
            CHECK (price >= 0 AND discount >= 0 AND amount >= 0)
        """)
        )

    # 外键：item_id -> items.id （SET NULL）
    fk_names = [fk.get("name") for fk in sa.inspect(bind).get_foreign_keys("order_items")]
    if FK_ORDER_ITEMS_ITEM not in fk_names:
        bind.execute(
            sa.text(f"""
            ALTER TABLE order_items
            ADD CONSTRAINT {FK_ORDER_ITEMS_ITEM}
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE SET NULL
        """)
        )

    # -------------------- order_address（幂等） --------------------
    if not _has_table(bind, "order_address"):
        op.create_table(
            "order_address",
            sa.Column(
                "order_id",
                sa.BigInteger(),
                sa.ForeignKey("orders.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("receiver_name", sa.String(255), nullable=True),
            sa.Column("receiver_phone", sa.String(64), nullable=True),
            sa.Column("province", sa.String(64), nullable=True),
            sa.Column("city", sa.String(64), nullable=True),
            sa.Column("district", sa.String(64), nullable=True),
            sa.Column("detail", sa.String(512), nullable=True),
            sa.Column("zipcode", sa.String(32), nullable=True),
        )

    # -------------------- order_logistics（幂等） --------------------
    if not _has_table(bind, "order_logistics"):
        op.create_table(
            "order_logistics",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column(
                "order_id",
                sa.BigInteger(),
                sa.ForeignKey("orders.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("carrier_code", sa.String(64), nullable=True),
            sa.Column("carrier_name", sa.String(128), nullable=True),
            sa.Column("tracking_no", sa.String(128), nullable=True, index=True),
            sa.Column("status", sa.String(32), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
    # 复合索引（若缺则补）
    bind.execute(
        sa.text(f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname='{IDX_ORDLOG_ORD_TRK}'
          ) THEN
            CREATE INDEX {IDX_ORDLOG_ORD_TRK} ON order_logistics(order_id, tracking_no);
          END IF;
        END $$;
    """)
    )


def downgrade() -> None:
    bind = op.get_bind()
    # 逆序清理（IF EXISTS 防御）
    bind.execute(sa.text(f"DROP INDEX IF EXISTS {IDX_ORDLOG_ORD_TRK}"))
    bind.execute(sa.text("DROP TABLE IF EXISTS order_logistics"))
    bind.execute(sa.text("DROP TABLE IF EXISTS order_address"))

    bind.execute(
        sa.text(
            f"ALTER TABLE IF EXISTS order_items DROP CONSTRAINT IF EXISTS {FK_ORDER_ITEMS_ITEM}"
        )
    )
    bind.execute(
        sa.text(
            f"ALTER TABLE IF EXISTS order_items DROP CONSTRAINT IF EXISTS {CHK_ORDER_ITEMS_AMT}"
        )
    )
    bind.execute(
        sa.text(
            f"ALTER TABLE IF EXISTS order_items DROP CONSTRAINT IF EXISTS {CHK_ORDER_ITEMS_QTY}"
        )
    )
    bind.execute(
        sa.text(
            f"ALTER TABLE IF EXISTS order_items DROP CONSTRAINT IF EXISTS {UQ_ORDER_ITEMS_ORD_SKU}"
        )
    )
    bind.execute(sa.text("DROP TABLE IF EXISTS order_items"))

    bind.execute(sa.text(f"DROP INDEX IF EXISTS {IDX_ORDERS_NO_TIME}"))
    bind.execute(
        sa.text(f"ALTER TABLE IF EXISTS orders DROP CONSTRAINT IF EXISTS {CHK_ORDERS_AMOUNT}")
    )
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders DROP COLUMN IF EXISTS pay_amount"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders DROP COLUMN IF EXISTS order_amount"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders DROP COLUMN IF EXISTS buyer_phone"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders DROP COLUMN IF EXISTS buyer_name"))
