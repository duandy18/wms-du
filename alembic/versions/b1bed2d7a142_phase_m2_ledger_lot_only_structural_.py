"""phase_m2: ledger lot-only structural finalization

Revision ID: b1bed2d7a142
Revises: a632b8a52669
Create Date: 2026-02-27

Lot-only structural universe:
- drop lot_id_key
- drop batch_code_key
- make lot_id NOT NULL
- unique constraint based only on lot_id
- index based on (item_id, warehouse_id, lot_id)
- rebuild reconcile view using pure lot_id
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1bed2d7a142"
down_revision: Union[str, Sequence[str], None] = "a632b8a52669"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --------------------------------------------------
    # 1️⃣ Drop dependent view first (uses lot_id_key)
    # --------------------------------------------------
    op.execute("DROP VIEW IF EXISTS v_stocks_lot_reconcile_receipt")

    # --------------------------------------------------
    # 2️⃣ Drop old unique constraint (contains batch_code_key)
    # --------------------------------------------------
    op.drop_constraint(
        "uq_ledger_wh_lot_batch_item_reason_ref_line",
        "stock_ledger",
        type_="unique",
    )

    # --------------------------------------------------
    # 3️⃣ Drop old structural index
    # --------------------------------------------------
    op.drop_index("ix_ledger_dims", table_name="stock_ledger")

    # --------------------------------------------------
    # 4️⃣ Drop legacy computed columns
    # --------------------------------------------------
    op.drop_column("stock_ledger", "batch_code_key")
    op.drop_column("stock_ledger", "lot_id_key")

    # --------------------------------------------------
    # 5️⃣ Enforce lot_id NOT NULL (structure anchor)
    # --------------------------------------------------
    op.alter_column(
        "stock_ledger",
        "lot_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # --------------------------------------------------
    # 6️⃣ Create new pure-lot unique constraint
    # --------------------------------------------------
    op.create_unique_constraint(
        "uq_ledger_wh_lot_item_reason_ref_line",
        "stock_ledger",
        [
            "reason",
            "ref",
            "ref_line",
            "item_id",
            "warehouse_id",
            "lot_id",
        ],
    )

    # --------------------------------------------------
    # 7️⃣ Create new structural index
    # --------------------------------------------------
    op.create_index(
        "ix_ledger_dims",
        "stock_ledger",
        ["item_id", "warehouse_id", "lot_id"],
    )

    # --------------------------------------------------
    # 8️⃣ Recreate reconcile view (lot-only)
    # --------------------------------------------------
    op.execute(
        """
        CREATE VIEW v_stocks_lot_reconcile_receipt AS
        WITH ledger_agg AS (
            SELECT
                item_id,
                warehouse_id,
                lot_id,
                SUM(delta)::integer AS qty
            FROM stock_ledger
            WHERE reason = 'RECEIPT'
            GROUP BY item_id, warehouse_id, lot_id
        ),
        stocks_agg AS (
            SELECT
                item_id,
                warehouse_id,
                lot_id,
                SUM(qty)::integer AS qty
            FROM stocks_lot
            GROUP BY item_id, warehouse_id, lot_id
        )
        SELECT
            COALESCE(s.item_id, a.item_id) AS item_id,
            COALESCE(s.warehouse_id, a.warehouse_id) AS warehouse_id,
            COALESCE(s.lot_id, a.lot_id) AS lot_id,
            COALESCE(s.qty, 0) AS stocks_qty,
            COALESCE(a.qty, 0) AS ledger_qty,
            COALESCE(s.qty, 0) - COALESCE(a.qty, 0) AS diff_qty
        FROM stocks_agg s
        FULL JOIN ledger_agg a
          ON a.item_id = s.item_id
         AND a.warehouse_id = s.warehouse_id
         AND a.lot_id = s.lot_id
        """
    )


def downgrade() -> None:
    raise Exception("Downgrade not supported for lot-only structural finalization.")
