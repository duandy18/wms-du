"""item_barcodes_cleanup

Revision ID: 9d277b13728b
Revises: 6bd0d6f7cb2a
Create Date: 2026-02-28 12:47:03.296996

- drop duplicate unique index on (barcode)
- drop duplicate FK on item_id
- enforce: primary barcode must be active
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d277b13728b'
down_revision: Union[str, Sequence[str], None] = '6bd0d6f7cb2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Drop duplicate unique index on barcode (keep uq_item_barcodes_barcode)
    op.execute(
        "DROP INDEX IF EXISTS public.item_barcodes_barcode_key"
    )

    # 2) Drop duplicate FK (keep the CASCADE one)
    op.execute(
        "ALTER TABLE public.item_barcodes "
        "DROP CONSTRAINT IF EXISTS item_barcodes_item_id_fkey1"
    )

    # 3) Harden semantics: primary barcode must be active
    op.create_check_constraint(
        "ck_item_barcodes_primary_must_be_active",
        "item_barcodes",
        sa.text("(NOT is_primary) OR active"),
    )


def downgrade() -> None:
    # 1) Drop the check constraint
    op.execute(
        "ALTER TABLE public.item_barcodes "
        "DROP CONSTRAINT IF EXISTS ck_item_barcodes_primary_must_be_active"
    )

    # 2) Recreate duplicate FK (historical state)
    op.execute(
        """
        ALTER TABLE public.item_barcodes
        ADD CONSTRAINT item_barcodes_item_id_fkey1
        FOREIGN KEY (item_id) REFERENCES public.items(id)
        """
    )

    # 3) Recreate duplicate unique index
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS item_barcodes_barcode_key "
        "ON public.item_barcodes USING btree (barcode)"
    )
