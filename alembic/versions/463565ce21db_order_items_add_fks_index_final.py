"""order_items add fks+index (final)

Revision ID: 463565ce21db
Revises: d824fa2ef8c8
Create Date: 2025-10-29 16:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "463565ce21db"
down_revision = "d824fa2ef8c8"
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()

    # 1) 复合索引（幂等）
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_order_items_order_item "
        "ON public.order_items (order_id, item_id)"
    ))

    # 2) 外键（幂等）
    existing_fks = {
        r[0] for r in conn.execute(sa.text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'public.order_items'::regclass"
        ))
    }

    if "fk_order_items_order" not in existing_fks:
        op.create_foreign_key(
            "fk_order_items_order",
            source_table="order_items",
            referent_table="orders",
            local_cols=["order_id"],
            remote_cols=["id"],
            ondelete="CASCADE",
            source_schema="public",
            referent_schema="public",
        )

    if "fk_order_items_item" not in existing_fks:
        op.create_foreign_key(
            "fk_order_items_item",
            source_table="order_items",
            referent_table="items",
            local_cols=["item_id"],
            remote_cols=["id"],
            source_schema="public",
            referent_schema="public",
        )

def downgrade():
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_order_items_order_item"))
    op.drop_constraint("fk_order_items_item", "order_items", type_="foreignkey")
    op.drop_constraint("fk_order_items_order", "order_items", type_="foreignkey")
