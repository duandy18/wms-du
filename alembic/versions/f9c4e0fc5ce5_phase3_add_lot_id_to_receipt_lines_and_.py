"""phase3 add lot_id to receipt_lines and ledger

Revision ID: f9c4e0fc5ce5
Revises: 818add26a746
Create Date: 2026-02-24 14:10:24.214251
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f9c4e0fc5ce5"
down_revision: Union[str, Sequence[str], None] = "818add26a746"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------
    # inbound_receipt_lines
    # ---------------------------
    op.add_column(
        "inbound_receipt_lines",
        sa.Column("lot_id", sa.Integer(), nullable=True),
    )

    op.create_foreign_key(
        "fk_inbound_receipt_lines_lot_id",
        "inbound_receipt_lines",
        "lots",
        ["lot_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # ---------------------------
    # stock_ledger
    # ---------------------------
    op.add_column(
        "stock_ledger",
        sa.Column("lot_id", sa.Integer(), nullable=True),
    )

    op.create_foreign_key(
        "fk_stock_ledger_lot_id",
        "stock_ledger",
        "lots",
        ["lot_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_stock_ledger_lot_id", "stock_ledger", type_="foreignkey")
    op.drop_column("stock_ledger", "lot_id")

    op.drop_constraint(
        "fk_inbound_receipt_lines_lot_id",
        "inbound_receipt_lines",
        type_="foreignkey",
    )
    op.drop_column("inbound_receipt_lines", "lot_id")
