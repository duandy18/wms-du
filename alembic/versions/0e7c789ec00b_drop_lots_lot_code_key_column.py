"""drop lots lot_code_key column

Revision ID: 0e7c789ec00b
Revises: d13519e5d5ac
Create Date: 2026-04-11 17:13:52.315969

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0e7c789ec00b"
down_revision: Union[str, Sequence[str], None] = "d13519e5d5ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index("ix_lots_wh_item_lot_code_key", table_name="lots")
    op.drop_column("lots", "lot_code_key")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("lots", sa.Column("lot_code_key", sa.Text(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE lots
               SET lot_code_key = upper(btrim(lot_code))
             WHERE lot_code IS NOT NULL
            """
        )
    )

    op.create_index(
        "ix_lots_wh_item_lot_code_key",
        "lots",
        ["warehouse_id", "item_id", "lot_code_key"],
        unique=False,
        postgresql_where=sa.text("lot_code IS NOT NULL"),
    )
