"""phase m4: replace batch_code with lot_code_input

Revision ID: e69ea88d6243
Revises: 5b4ff22a3818
Create Date: 2026-03-01 13:52:59.455141

- add lot_code_input (supplier lot code input)
- migrate existing inbound_receipt_lines.batch_code to lot_code_input
- drop legacy batch_code column
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e69ea88d6243"
down_revision: Union[str, Sequence[str], None] = "5b4ff22a3818"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) add new supplier lot input field
    op.add_column(
        "inbound_receipt_lines",
        sa.Column("lot_code_input", sa.String(length=64), nullable=True),
    )

    # 2) migrate existing batch_code data
    op.execute(
        """
UPDATE inbound_receipt_lines
SET lot_code_input = batch_code
WHERE batch_code IS NOT NULL;
"""
    )

    # 3) drop old batch_code
    op.drop_column("inbound_receipt_lines", "batch_code")


def downgrade() -> None:
    """Downgrade schema."""

    # restore batch_code
    op.add_column(
        "inbound_receipt_lines",
        sa.Column("batch_code", sa.String(length=64), nullable=True),
    )

    # migrate back
    op.execute(
        """
UPDATE inbound_receipt_lines
SET batch_code = lot_code_input
WHERE lot_code_input IS NOT NULL;
"""
    )

    op.drop_column("inbound_receipt_lines", "lot_code_input")
