"""switch lots required identity unique to production_date

Revision ID: d13519e5d5ac
Revises: 763cb99a6e13
Create Date: 2026-04-11 16:22:05.964900

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d13519e5d5ac"
down_revision: Union[str, Sequence[str], None] = "763cb99a6e13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index("uq_lots_wh_item_lot_code_key", table_name="lots")
    op.drop_index("ix_lots_wh_item_production_date", table_name="lots")

    op.create_check_constraint(
        "ck_lots_production_date_by_expiry_policy",
        "lots",
        "("
        "(item_expiry_policy_snapshot = 'REQUIRED' AND production_date IS NOT NULL) OR "
        "(item_expiry_policy_snapshot <> 'REQUIRED' AND production_date IS NULL)"
        ")",
    )

    op.create_check_constraint(
        "ck_lots_required_supplier_source",
        "lots",
        "("
        "item_expiry_policy_snapshot <> 'REQUIRED' OR "
        "lot_code_source = 'SUPPLIER'"
        ")",
    )

    op.create_index(
        "uq_lots_required_single_wh_item_prod",
        "lots",
        ["warehouse_id", "item_id", "production_date"],
        unique=True,
        postgresql_where=sa.text(
            "lot_code_source = 'SUPPLIER' "
            "AND item_expiry_policy_snapshot = 'REQUIRED' "
            "AND production_date IS NOT NULL"
        ),
    )

    op.create_index(
        "ix_lots_wh_item_lot_code_key",
        "lots",
        ["warehouse_id", "item_id", "lot_code_key"],
        unique=False,
        postgresql_where=sa.text("lot_code IS NOT NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_lots_wh_item_lot_code_key", table_name="lots")
    op.drop_index("uq_lots_required_single_wh_item_prod", table_name="lots")

    op.drop_constraint("ck_lots_required_supplier_source", "lots", type_="check")
    op.drop_constraint("ck_lots_production_date_by_expiry_policy", "lots", type_="check")

    op.create_index(
        "ix_lots_wh_item_production_date",
        "lots",
        ["warehouse_id", "item_id", "production_date"],
        unique=False,
        postgresql_where=sa.text("production_date IS NOT NULL"),
    )

    op.create_index(
        "uq_lots_wh_item_lot_code_key",
        "lots",
        ["warehouse_id", "item_id", "lot_code_key"],
        unique=True,
        postgresql_where=sa.text("lot_code IS NOT NULL"),
    )
