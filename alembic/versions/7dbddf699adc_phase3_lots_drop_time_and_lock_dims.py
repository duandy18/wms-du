"""phase3_lots_drop_time_and_lock_dims

Revision ID: 7dbddf699adc
Revises: ae2f601d7927
Create Date: 2026-02-28 13:02:50.104942

Phase 3 structural closure:

1) Remove time semantics from lots (production/expiry/...).
   Canonical lot dates live ONLY in stock_ledger (RECEIPT rows).

2) Enforce lot dimension consistency:
   (lot_id, warehouse_id, item_id) must match lots(id, warehouse_id, item_id).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7dbddf699adc"
down_revision: Union[str, Sequence[str], None] = "ae2f601d7927"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1) Drop time-related columns from lots
    # ------------------------------------------------------------------
    with op.batch_alter_table("lots") as bop:
        bop.drop_column("production_date")
        bop.drop_column("expiry_date")
        bop.drop_column("expiry_source")
        bop.drop_column("shelf_life_days_applied")

    # ------------------------------------------------------------------
    # 2) Add composite unique key on lots to support composite FK
    # ------------------------------------------------------------------
    op.create_unique_constraint(
        "uq_lots_id_wh_item",
        "lots",
        ["id", "warehouse_id", "item_id"],
    )

    # ------------------------------------------------------------------
    # 3) Replace stock_ledger FK(lot_id) -> lots(id)
    #    with composite FK(lot_id, warehouse_id, item_id)
    # ------------------------------------------------------------------
    op.drop_constraint(
        "fk_stock_ledger_lot_id",
        "stock_ledger",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_stock_ledger_lot_dims",
        "stock_ledger",
        "lots",
        ["lot_id", "warehouse_id", "item_id"],
        ["id", "warehouse_id", "item_id"],
        ondelete="RESTRICT",
    )

    # ------------------------------------------------------------------
    # 4) Replace stocks_lot FK(lot_id) -> lots(id)
    #    with composite FK(lot_id, warehouse_id, item_id)
    # ------------------------------------------------------------------
    op.drop_constraint(
        "fk_stocks_lot_lot_id",
        "stocks_lot",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_stocks_lot_lot_dims",
        "stocks_lot",
        "lots",
        ["lot_id", "warehouse_id", "item_id"],
        ["id", "warehouse_id", "item_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 4) Revert stocks_lot composite FK
    # ------------------------------------------------------------------
    op.drop_constraint(
        "fk_stocks_lot_lot_dims",
        "stocks_lot",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_stocks_lot_lot_id",
        "stocks_lot",
        "lots",
        ["lot_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # ------------------------------------------------------------------
    # 3) Revert stock_ledger composite FK
    # ------------------------------------------------------------------
    op.drop_constraint(
        "fk_stock_ledger_lot_dims",
        "stock_ledger",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_stock_ledger_lot_id",
        "stock_ledger",
        "lots",
        ["lot_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # ------------------------------------------------------------------
    # 2) Drop composite unique
    # ------------------------------------------------------------------
    op.drop_constraint(
        "uq_lots_id_wh_item",
        "lots",
        type_="unique",
    )

    # ------------------------------------------------------------------
    # 1) Restore dropped columns
    # ------------------------------------------------------------------
    with op.batch_alter_table("lots") as bop:
        bop.add_column(sa.Column("production_date", sa.Date(), nullable=True))
        bop.add_column(sa.Column("expiry_date", sa.Date(), nullable=True))
        bop.add_column(sa.Column("expiry_source", sa.String(length=16), nullable=True))
        bop.add_column(sa.Column("shelf_life_days_applied", sa.Integer(), nullable=True))
