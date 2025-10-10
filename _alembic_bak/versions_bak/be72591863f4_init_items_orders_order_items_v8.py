import sqlalchemy as sa

from alembic import op

revision = "be72591863f4"
down_revision = "495074aac8bf"
branch_labels = None
depends_on = None


def upgrade():
    # items
    op.create_table(
        "items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("barcode", sa.String(64), nullable=True),
        sa.Column("uom", sa.String(16), nullable=False, server_default="EA"),
        sa.Column("price", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "INACTIVE", name="item_status"),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.UniqueConstraint("sku", name="uq_items_sku"),
        sa.UniqueConstraint("barcode", name="uq_items_barcode"),
    )
    op.create_index("ix_items_sku", "items", ["sku"])
    op.create_index("ix_items_status", "items", ["status"])

    # orders
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("order_no", sa.String(32), nullable=False),
        sa.Column("order_type", sa.Enum("SALES", "PURCHASE", name="order_type"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "CONFIRMED", "FULFILLED", "CANCELED", name="order_status"),
            nullable=False,
        ),
        sa.Column("customer_name", sa.String(255), nullable=True),
        sa.Column("supplier_name", sa.String(255), nullable=True),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.UniqueConstraint("order_no", name="uq_orders_order_no"),
    )
    op.create_index("ix_orders_order_no", "orders", ["order_no"])
    op.create_index("ix_orders_order_type", "orders", ["order_type"])
    op.create_index("ix_orders_status", "orders", ["status"])

    # order_items
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "order_id", sa.Integer, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "item_id", sa.Integer, sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("line_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_item_id", "order_items", ["item_id"])


def downgrade():
    op.drop_table("order_items")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_order_type", table_name="orders")
    op.drop_index("ix_orders_order_no", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_items_status", table_name="items")
    op.drop_index("ix_items_sku", table_name="items")
    op.drop_table("items")
    # PostgreSQL 下用于清理枚举；SQLite 下通常不是实体 TYPE
    op.execute("DROP TYPE IF EXISTS item_status")
    op.execute("DROP TYPE IF EXISTS order_type")
    op.execute("DROP TYPE IF EXISTS order_status")
