"""channel_reserve_ops (idempotency for reserve)
Revision ID: 20251026_channel_reserve_ops
Revises: 0dc82617dd9c
Create Date: 2025-10-26 16:20:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251026_channel_reserve_ops"
down_revision = "0dc82617dd9c"  # 如与你仓当前 head 不同，请改为实际 head
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "channel_reserve_ops",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "store_id", sa.Integer, sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("ext_order_id", sa.String(64), nullable=False),
        sa.Column("ext_sku_id", sa.String(64), nullable=False),
        sa.Column("op", sa.String(16), nullable=False, server_default="RESERVE"),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "store_id", "ext_order_id", "ext_sku_id", "op", name="uq_reserve_idem_key"
        ),
    )
    op.create_index(
        "ix_reserve_ops_store_order",
        "channel_reserve_ops",
        ["store_id", "ext_order_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_reserve_ops_store_order", table_name="channel_reserve_ops")
    op.drop_table("channel_reserve_ops")
