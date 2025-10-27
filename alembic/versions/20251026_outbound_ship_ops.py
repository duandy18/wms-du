"""outbound_ship_ops (idempotency for ship)

Revision ID: 20251026_outbound_ship_ops
Revises: 20251026_channel_reserve_ops
Create Date: 2025-10-26 17:10:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251026_outbound_ship_ops"
down_revision = "20251026_channel_reserve_ops"  # 你当前数据库的 head
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "outbound_ship_ops",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("store_id", sa.Integer, sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ref", sa.String(128), nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("store_id", "ref", "item_id", "location_id", name="uq_ship_idem_key"),
    )
    op.create_index("ix_ship_ops_store_ref", "outbound_ship_ops", ["store_id", "ref"], unique=False)


def downgrade():
    op.drop_index("ix_ship_ops_store_ref", table_name="outbound_ship_ops")
    op.drop_table("outbound_ship_ops")
