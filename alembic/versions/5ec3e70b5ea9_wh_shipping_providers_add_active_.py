"""wh_shipping_providers_add_active_template_id

Revision ID: 5ec3e70b5ea9
Revises: 116cb813537d
Create Date: 2026-03-20 18:37:01.134391

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5ec3e70b5ea9"
down_revision: Union[str, Sequence[str], None] = "116cb813537d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. add column
    op.add_column(
        "warehouse_shipping_providers",
        sa.Column("active_template_id", sa.Integer(), nullable=True),
    )

    # 2. add foreign key
    op.create_foreign_key(
        "fk_wh_shipping_providers_active_template_id",
        "warehouse_shipping_providers",
        "shipping_provider_pricing_templates",
        ["active_template_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. add index
    op.create_index(
        "ix_wh_shipping_providers_active_template_id",
        "warehouse_shipping_providers",
        ["active_template_id"],
        unique=False,
    )


def downgrade() -> None:
    # reverse order

    op.drop_index(
        "ix_wh_shipping_providers_active_template_id",
        table_name="warehouse_shipping_providers",
    )

    op.drop_constraint(
        "fk_wh_shipping_providers_active_template_id",
        "warehouse_shipping_providers",
        type_="foreignkey",
    )

    op.drop_column("warehouse_shipping_providers", "active_template_id")
