"""phase4a1: ledger idempotency key include lot_id_key

Revision ID: 4259e5deb13b
Revises: f9c4e0fc5ce5
Create Date: 2026-02-24 16:51:49.705008

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4259e5deb13b"
down_revision: Union[str, Sequence[str], None] = "f9c4e0fc5ce5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase 4A-1

    1) introduce lot_id_key (generated stored)
    2) enforce NOT NULL + index for lot_id_key (align ORM / alembic-check)
    3) create new idempotency unique constraint including lot_id_key
    4) drop legacy unique constraint (batch-only world)
    """

    # 1) add generated column
    op.execute(
        """
        ALTER TABLE stock_ledger
        ADD COLUMN lot_id_key integer
        GENERATED ALWAYS AS (COALESCE(lot_id, 0)) STORED;
        """
    )

    # 2) align with ORM: NOT NULL + index
    op.execute(
        """
        ALTER TABLE stock_ledger
        ALTER COLUMN lot_id_key SET NOT NULL;
        """
    )

    op.create_index(
        "ix_stock_ledger_lot_id_key",
        "stock_ledger",
        ["lot_id_key"],
    )

    # 3) create new unique constraint (lot-aware idempotency key)
    op.execute(
        """
        ALTER TABLE stock_ledger
        ADD CONSTRAINT uq_ledger_wh_lot_batch_item_reason_ref_line
        UNIQUE (
            reason,
            ref,
            ref_line,
            item_id,
            warehouse_id,
            lot_id_key,
            batch_code_key
        );
        """
    )

    # 4) drop legacy constraint (batch-only idempotency)
    op.execute(
        """
        ALTER TABLE stock_ledger
        DROP CONSTRAINT uq_ledger_wh_batch_item_reason_ref_line;
        """
    )


def downgrade() -> None:
    """
    Rollback Phase 4A-1

    Reverse order:
    1) restore legacy unique constraint
    2) drop new lot-aware constraint
    3) drop index on lot_id_key (IF EXISTS for backward-compat with older applied revision)
    4) drop generated column
    """

    # 1) restore legacy unique constraint
    op.execute(
        """
        ALTER TABLE stock_ledger
        ADD CONSTRAINT uq_ledger_wh_batch_item_reason_ref_line
        UNIQUE (
            reason,
            ref,
            ref_line,
            item_id,
            batch_code_key,
            warehouse_id
        );
        """
    )

    # 2) drop new constraint
    op.execute(
        """
        ALTER TABLE stock_ledger
        DROP CONSTRAINT uq_ledger_wh_lot_batch_item_reason_ref_line;
        """
    )

    # 3) drop index first (must happen before dropping the column)
    # Use IF EXISTS: this revision may have been applied before index creation was added.
    op.execute(
        """
        DROP INDEX IF EXISTS ix_stock_ledger_lot_id_key;
        """
    )

    # 4) drop generated column
    op.execute(
        """
        ALTER TABLE stock_ledger
        DROP COLUMN lot_id_key;
        """
    )
