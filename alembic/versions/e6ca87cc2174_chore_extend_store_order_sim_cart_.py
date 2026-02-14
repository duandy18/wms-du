"""chore_extend_store_order_sim_cart_address_fields

Revision ID: e6ca87cc2174
Revises: 10a222ee994f
Create Date: 2026-02-14 02:40:48.299140

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6ca87cc2174"
down_revision: Union[str, Sequence[str], None] = "10a222ee994f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("store_order_sim_cart", sa.Column("district", sa.String(length=128), nullable=True))
    op.add_column("store_order_sim_cart", sa.Column("detail", sa.String(length=512), nullable=True))
    op.add_column("store_order_sim_cart", sa.Column("receiver_name", sa.String(length=128), nullable=True))
    op.add_column("store_order_sim_cart", sa.Column("receiver_phone", sa.String(length=64), nullable=True))
    op.add_column("store_order_sim_cart", sa.Column("zipcode", sa.String(length=32), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("store_order_sim_cart", "zipcode")
    op.drop_column("store_order_sim_cart", "receiver_phone")
    op.drop_column("store_order_sim_cart", "receiver_name")
    op.drop_column("store_order_sim_cart", "detail")
    op.drop_column("store_order_sim_cart", "district")
