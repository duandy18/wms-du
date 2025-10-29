"""order_items add foreign keys and index

Revision ID: d824fa2ef8c8
Revises: cfb24bbca2a0
Create Date: 2025-10-29 15:20:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "d824fa2ef8c8"
down_revision = "cfb24bbca2a0"
branch_labels = None
depends_on = None


def upgrade():
    # 幂等创建复合索引（PG 支持 IF NOT EXISTS）
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_order_items_order_item "
        "ON order_items (order_id, item_id)"
    ))

    # 幂等创建外键
    conn = op.get_bind()
    fk_names = [r[0] for r in conn.execute(sa.text("""
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'order_items'::regclass
    """)).fetchall()]

    if "fk_order_items_order" not in fk_names:
        op.create_foreign_key(
            "fk_order_items_order",
            "order_items", "orders",
            ["order_id"], ["id"],
            ondelete="CASCADE",
        )
    if "fk_order_items_item" not in fk_names:
        op.create_foreign_key(
            "fk_order_items_item",
            "order_items", "items",
            ["item_id"], ["id"],
        )


def downgrade():
    # 幂等删除索引与外键
    op.execute(sa.text("DROP INDEX IF EXISTS ix_order_items_order_item"))
    op.drop_constraint("fk_order_items_item", "order_items", type_="foreignkey")
    op.drop_constraint("fk_order_items_order", "order_items", type_="foreignkey")
