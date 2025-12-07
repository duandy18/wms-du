"""create order_state_snapshot (platform, shop_id, order_no) -> state

Revision ID: u9_order_state_snapshot
Revises: u8_items_unit_default
Create Date: 2025-10-23
"""

from alembic import op
import sqlalchemy as sa

revision = "u9_order_state_snapshot"
down_revision = "u8_items_unit_default"  # ← 按你的链路调整为当前 head
branch_labels = None
depends_on = None


def _is_sqlite(bind) -> bool:
    return (bind.dialect.name or "").lower() == "sqlite"


def upgrade():
    bind = op.get_bind()
    sqlite = _is_sqlite(bind)

    # 避免重复建表：检查是否已存在
    insp = sa.inspect(bind)
    if "order_state_snapshot" not in insp.get_table_names(schema="public" if not sqlite else None):
        op.create_table(
            "order_state_snapshot",
            sa.Column(
                "id",
                sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
                primary_key=True,
                autoincrement=True,
            ),
            sa.Column("platform", sa.String(32), nullable=False),
            sa.Column("shop_id", sa.String(64), nullable=False),
            sa.Column("order_no", sa.String(128), nullable=False),
            sa.Column("state", sa.String(32), nullable=False),
            sa.Column(
                "updated_at",
                sa.TIMESTAMP(timezone=not sqlite),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP" if sqlite else "now()"),
            ),
            sa.UniqueConstraint(
                "platform", "shop_id", "order_no", name="uq_order_state_snapshot_key"
            ),
        )
        op.create_index(
            "ix_order_state_snapshot_lookup",
            "order_state_snapshot",
            ["platform", "shop_id", "order_no"],
            unique=True,
        )


def downgrade():
    op.drop_index("ix_order_state_snapshot_lookup", table_name="order_state_snapshot")
    op.drop_table("order_state_snapshot")
