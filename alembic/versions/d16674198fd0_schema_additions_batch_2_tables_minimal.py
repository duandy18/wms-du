"""schema additions batch-2 (tables minimal)

Revision ID: d16674198fd0
Revises: 6869fc360d86
Create Date: 2025-10-29 19:40:00
"""
from alembic import op
import sqlalchemy as sa

revision = "d16674198fd0"
down_revision = "6869fc360d86"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------
    # 1) parties（最小结构）
    # ------------------------------
    op.create_table(
        "parties",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("party_type", sa.String(32), nullable=False),  # customer/supplier/...
        schema="public",
    )
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_parties_id   ON public.parties (id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_parties_name ON public.parties (name)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_parties_type ON public.parties (party_type)"))

    # ------------------------------
    # 2) return_records（最小结构）
    # ------------------------------
    op.create_table(
        "return_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("order_id", sa.Integer, nullable=False),
        sa.Column("product_id", sa.Integer, nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        schema="public",
    )
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_return_records_id      ON public.return_records (id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_return_records_order   ON public.return_records (order_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_return_records_product ON public.return_records (product_id)"))

    # ------------------------------
    # 3) inventory_movements（最小结构）
    # ------------------------------
    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("item_sku", sa.String(64), nullable=False),
        sa.Column("movement_type", sa.String(32), nullable=False),  # inbound/outbound/adjust/...
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="public",
    )
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_inventory_movements_id         ON public.inventory_movements (id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_inventory_movements_item_sku   ON public.inventory_movements (item_sku)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_inventory_movements_move_type ON public.inventory_movements (movement_type)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_inventory_movements_sku_time  ON public.inventory_movements (item_sku, timestamp)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_inventory_movements_type_time ON public.inventory_movements (movement_type, timestamp)"))


def downgrade():
    op.drop_table("inventory_movements", schema="public")
    op.drop_table("return_records", schema="public")
    op.drop_table("parties", schema="public")
