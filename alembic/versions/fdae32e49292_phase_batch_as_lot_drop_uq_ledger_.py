"""phase batch-as-lot: drop uq_ledger_receipt_wh_lot

Revision ID: fdae32e49292
Revises: 21a347e34ad3
Create Date: 2026-03-04 18:12:59.984689

Batch-as-Lot Phase 1:
- allow multiple RECEIPT ledger rows per (warehouse_id, lot_id)
- idempotency remains on uq_ledger_wh_lot_item_reason_ref_line
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "fdae32e49292"
down_revision: Union[str, Sequence[str], None] = "21a347e34ad3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop partial unique index: one RECEIPT per (warehouse_id, lot_id)
    op.drop_index("uq_ledger_receipt_wh_lot", table_name="stock_ledger")


def downgrade() -> None:
    # Restore original behavior (pre Batch-as-Lot Phase 1)
    op.create_index(
        "uq_ledger_receipt_wh_lot",
        "stock_ledger",
        ["warehouse_id", "lot_id"],
        unique=True,
        postgresql_where=sa.text("(reason_canon)::text = 'RECEIPT'::text"),
    )
