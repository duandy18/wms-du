"""expand_order_shipment_prepare_packages_for_multi_warehouse

Revision ID: 43378845be11
Revises: 7ccf9fd0b806
Create Date: 2026-03-24 20:10:46.744308

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '43378845be11'
down_revision: Union[str, Sequence[str], None] = '7ccf9fd0b806'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "order_shipment_prepare_packages",
        sa.Column(
            "warehouse_id",
            sa.Integer(),
            nullable=True,
            comment="该包裹选定发货仓 warehouses.id",
        ),
    )
    op.add_column(
        "order_shipment_prepare_packages",
        sa.Column(
            "pricing_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
            comment="该包裹运价状态：pending / calculated",
        ),
    )
    op.add_column(
        "order_shipment_prepare_packages",
        sa.Column(
            "selected_provider_id",
            sa.Integer(),
            nullable=True,
            comment="该包裹已选承运商 shipping_providers.id",
        ),
    )
    op.add_column(
        "order_shipment_prepare_packages",
        sa.Column(
            "selected_quote_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="该包裹已锁定报价快照",
        ),
    )

    op.create_foreign_key(
        "order_shipment_prepare_packages_warehouse_id_fkey",
        "order_shipment_prepare_packages",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "order_shipment_prepare_packages_selected_provider_id_fkey",
        "order_shipment_prepare_packages",
        "shipping_providers",
        ["selected_provider_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_check_constraint(
        "ck_order_shipment_prepare_packages_pricing_status",
        "order_shipment_prepare_packages",
        "pricing_status IN ('pending', 'calculated')",
    )

    op.create_index(
        "ix_order_shipment_prepare_packages_warehouse_id",
        "order_shipment_prepare_packages",
        ["warehouse_id"],
        unique=False,
    )
    op.create_index(
        "ix_order_shipment_prepare_packages_pricing_status",
        "order_shipment_prepare_packages",
        ["pricing_status"],
        unique=False,
    )
    op.create_index(
        "ix_order_shipment_prepare_packages_selected_provider_id",
        "order_shipment_prepare_packages",
        ["selected_provider_id"],
        unique=False,
    )

    op.alter_column(
        "order_shipment_prepare_packages",
        "pricing_status",
        server_default=None,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_order_shipment_prepare_packages_selected_provider_id",
        table_name="order_shipment_prepare_packages",
    )
    op.drop_index(
        "ix_order_shipment_prepare_packages_pricing_status",
        table_name="order_shipment_prepare_packages",
    )
    op.drop_index(
        "ix_order_shipment_prepare_packages_warehouse_id",
        table_name="order_shipment_prepare_packages",
    )

    op.drop_constraint(
        "ck_order_shipment_prepare_packages_pricing_status",
        "order_shipment_prepare_packages",
        type_="check",
    )

    op.drop_constraint(
        "order_shipment_prepare_packages_selected_provider_id_fkey",
        "order_shipment_prepare_packages",
        type_="foreignkey",
    )
    op.drop_constraint(
        "order_shipment_prepare_packages_warehouse_id_fkey",
        "order_shipment_prepare_packages",
        type_="foreignkey",
    )

    op.drop_column("order_shipment_prepare_packages", "selected_quote_snapshot")
    op.drop_column("order_shipment_prepare_packages", "selected_provider_id")
    op.drop_column("order_shipment_prepare_packages", "pricing_status")
    op.drop_column("order_shipment_prepare_packages", "warehouse_id")
