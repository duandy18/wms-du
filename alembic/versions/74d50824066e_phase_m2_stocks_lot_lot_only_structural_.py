"""phase_m2: stocks_lot lot-only structural finalization

Revision ID: 74d50824066e
Revises: b1bed2d7a142

Lot-only structural universe for stocks_lot:
- drop lot_id_key
- make lot_id NOT NULL
- unique constraint only based on lot_id
- rebuild index based on (item_id, warehouse_id, lot_id)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "74d50824066e"
down_revision: Union[str, Sequence[str], None] = "b1bed2d7a142"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --------------------------------------------------
    # 1️⃣ Drop old unique constraint (based on lot_id_key)
    # --------------------------------------------------
    op.drop_constraint(
        "uq_stocks_lot_item_wh_lot",
        "stocks_lot",
        type_="unique",
    )

    # --------------------------------------------------
    # 2️⃣ Drop old index
    # --------------------------------------------------
    op.drop_index("ix_stocks_lot_item_wh_lot", table_name="stocks_lot")

    # --------------------------------------------------
    # 3️⃣ Drop legacy lot_id_key column
    # --------------------------------------------------
    op.drop_column("stocks_lot", "lot_id_key")

    # --------------------------------------------------
    # 4️⃣ Enforce lot_id NOT NULL (structure anchor)
    # --------------------------------------------------
    op.alter_column(
        "stocks_lot",
        "lot_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # --------------------------------------------------
    # 5️⃣ Create new pure-lot unique constraint
    # --------------------------------------------------
    op.create_unique_constraint(
        "uq_stocks_lot_item_wh_lot",
        "stocks_lot",
        ["item_id", "warehouse_id", "lot_id"],
    )

    # --------------------------------------------------
    # 6️⃣ Create new structural index
    # --------------------------------------------------
    op.create_index(
        "ix_stocks_lot_item_wh_lot",
        "stocks_lot",
        ["item_id", "warehouse_id", "lot_id"],
    )


def downgrade() -> None:
    raise Exception("Downgrade not supported for lot-only structural finalization.")
