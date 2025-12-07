"""add purchase_orders table

Revision ID: ac53a14e9f34
Revises: 7150a6cf6d79
Create Date: 2025-11-27 17:14:14.496400
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ac53a14e9f34"
down_revision: Union[str, Sequence[str], None] = "7150a6cf6d79"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ------------ Infra utils（与你项目保持完全一致风格） ------------

def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return insp.has_table(name)  # type: ignore[attr-defined]
    except Exception:
        return name in insp.get_table_names()


def _index_names(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return {ix["name"] for ix in insp.get_indexes(table)}
    except Exception:
        return set()


# ------------------------------ upgrade ------------------------------

def upgrade() -> None:
    if not _has_table("purchase_orders"):
        op.create_table(
            "purchase_orders",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("supplier", sa.String(length=100), nullable=False),
            sa.Column("warehouse_id", sa.Integer(), nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("qty_ordered", sa.Integer(), nullable=False),
            sa.Column("qty_received", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="CREATED",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "last_received_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            sa.Column(
                "closed_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            sa.ForeignKeyConstraint(
                ["warehouse_id"],
                ["warehouses.id"],
                name="fk_po_warehouse",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["item_id"],
                ["items.id"],
                name="fk_po_item",
                ondelete="RESTRICT",
            ),
        )

    idx = _index_names("purchase_orders")
    if "ix_purchase_orders_wh_item_status" not in idx:
        op.create_index(
            "ix_purchase_orders_wh_item_status",
            "purchase_orders",
            ["warehouse_id", "item_id", "status"],
            unique=False,
        )
    if "ix_purchase_orders_supplier" not in idx:
        op.create_index(
            "ix_purchase_orders_supplier",
            "purchase_orders",
            ["supplier"],
            unique=False,
        )


# ------------------------------ downgrade ------------------------------

def downgrade() -> None:
    if _has_table("purchase_orders"):
        idx = _index_names("purchase_orders")
        if "ix_purchase_orders_wh_item_status" in idx:
            op.drop_index(
                "ix_purchase_orders_wh_item_status", table_name="purchase_orders"
            )
        if "ix_purchase_orders_supplier" in idx:
            op.drop_index(
                "ix_purchase_orders_supplier", table_name="purchase_orders"
            )

        op.drop_table("purchase_orders")
