"""ledger_lock_inbound_snapshot_semantics

Revision ID: ae2f601d7927
Revises: 9d277b13728b
Create Date: 2026-02-28 12:48:13.409786

Phase 3: lock stock_ledger as the ONLY canonical source of lot dates.

- Clean polluted dates on non-RECEIPT rows.
- Enforce: only RECEIPT rows may carry production/expiry dates.
- Enforce: at most one RECEIPT per (warehouse_id, lot_id).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ae2f601d7927'
down_revision: Union[str, Sequence[str], None] = '9d277b13728b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 0) Data fix: remove date pollution from non-RECEIPT rows
    # ------------------------------------------------------------------
    op.execute(
        """
        UPDATE public.stock_ledger
        SET production_date = NULL,
            expiry_date = NULL
        WHERE reason_canon <> 'RECEIPT'
          AND (production_date IS NOT NULL OR expiry_date IS NOT NULL)
        """
    )

    # ------------------------------------------------------------------
    # 1) CHECK: only RECEIPT rows may carry dates
    # ------------------------------------------------------------------
    op.create_check_constraint(
        "ck_ledger_dates_only_on_receipt",
        "stock_ledger",
        sa.text(
            "(reason_canon = 'RECEIPT') "
            "OR (production_date IS NULL AND expiry_date IS NULL)"
        ),
    )

    # ------------------------------------------------------------------
    # 2) Partial UNIQUE: one RECEIPT per (warehouse_id, lot_id)
    # ------------------------------------------------------------------
    op.create_index(
        "uq_ledger_receipt_wh_lot",
        "stock_ledger",
        ["warehouse_id", "lot_id"],
        unique=True,
        postgresql_where=sa.text("reason_canon = 'RECEIPT'"),
    )


def downgrade() -> None:
    # Drop partial unique index
    op.drop_index(
        "uq_ledger_receipt_wh_lot",
        table_name="stock_ledger",
    )

    # Drop CHECK constraint
    op.execute(
        "ALTER TABLE public.stock_ledger "
        "DROP CONSTRAINT IF EXISTS ck_ledger_dates_only_on_receipt"
    )

    # NOTE:
    # We do NOT restore previously polluted dates.
    # That data was structurally invalid and intentionally removed.
