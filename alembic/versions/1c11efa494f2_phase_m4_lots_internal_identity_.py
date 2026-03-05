"""phase m4: lots internal identity constraints

Revision ID: 1c11efa494f2
Revises: 116a1292c058
Create Date: 2026-03-01 12:50:11.444747

- enforce INTERNAL lot identity by (warehouse_id, item_id, source_receipt_id, source_line_no)
- enforce INTERNAL requires source_receipt_id/source_line_no
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1c11efa494f2"
down_revision: Union[str, Sequence[str], None] = "116a1292c058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ------------------------------------------------------------------
    # 1) INTERNAL lot must have source_receipt_id/source_line_no
    # ------------------------------------------------------------------
    op.create_check_constraint(
        "ck_lots_internal_requires_source_receipt_line",
        "lots",
        sa.text(
            "(lot_code_source <> 'INTERNAL') "
            "OR (source_receipt_id IS NOT NULL AND source_line_no IS NOT NULL)"
        ),
    )

    # ------------------------------------------------------------------
    # 2) INTERNAL identity unique anchor (partial unique index)
    #    (warehouse_id, item_id, source_receipt_id, source_line_no)
    # ------------------------------------------------------------------
    op.create_index(
        "uq_lots_internal_wh_item_src_receipt_line",
        "lots",
        ["warehouse_id", "item_id", "source_receipt_id", "source_line_no"],
        unique=True,
        postgresql_where=sa.text("lot_code_source = 'INTERNAL'"),
    )


def downgrade() -> None:
    """Downgrade schema."""

    # Drop INTERNAL identity unique index
    op.drop_index(
        "uq_lots_internal_wh_item_src_receipt_line",
        table_name="lots",
        postgresql_where=sa.text("lot_code_source = 'INTERNAL'"),
    )

    # Drop INTERNAL source requirement check
    op.drop_constraint(
        "ck_lots_internal_requires_source_receipt_line",
        "lots",
        type_="check",
    )
