"""add store_id to orders and backfill

Revision ID: 18f7a496ed6d
Revises: aa0ebff00956
Create Date: 2026-03-29 14:42:55.582960

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "18f7a496ed6d"
down_revision: Union[str, Sequence[str], None] = "aa0ebff00956"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "orders",
        sa.Column(
            "store_id",
            sa.BigInteger(),
            nullable=True,
            comment="内部店铺主键（stores.id）",
        ),
    )

    op.create_index("ix_orders_store_id", "orders", ["store_id"], unique=False)

    op.create_foreign_key(
        "fk_orders_store_id_stores",
        "orders",
        "stores",
        ["store_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.execute(
        """
        UPDATE orders o
        SET store_id = s.id
        FROM stores s
        WHERE o.store_id IS NULL
          AND s.platform = o.platform
          AND s.shop_id = o.shop_id
        """
    )

    conn = op.get_bind()
    missing = conn.execute(
        sa.text(
            """
            SELECT count(*) AS cnt
            FROM orders
            WHERE store_id IS NULL
            """
        )
    ).scalar_one()

    if int(missing or 0) > 0:
        raise RuntimeError(
            f"orders.store_id backfill failed: {int(missing)} rows still NULL"
        )

    op.alter_column("orders", "store_id", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint("fk_orders_store_id_stores", "orders", type_="foreignkey")
    op.drop_index("ix_orders_store_id", table_name="orders")
    op.drop_column("orders", "store_id")
