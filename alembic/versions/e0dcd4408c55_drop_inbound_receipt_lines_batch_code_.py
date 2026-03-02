"""drop inbound_receipt_lines batch_code and triple-truth snapshots

Revision ID: e0dcd4408c55
Revises: 1eed14aa1510
Create Date: 2026-02-28 13:29:09.345242

Phase 3:

- Remove batch_code from inbound_receipt_lines (lot-only identity; lot_code lives on lots).
- Remove triple-truth item snapshot fields from inbound_receipt_lines:
  item_name, item_sku, category, spec_text, base_uom, purchase_uom, barcode

Keep:
- item_id / po_line_id (source anchor)
- lot_id (identity anchor)
- production_date / expiry_date (INPUT only; canonical dates live in stock_ledger RECEIPT)
- qty & money fields

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e0dcd4408c55"
down_revision: Union[str, Sequence[str], None] = "1eed14aa1510"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # index depends on batch_code
    op.execute("DROP INDEX IF EXISTS public.ix_inbound_receipt_lines_item_batch")

    with op.batch_alter_table("inbound_receipt_lines") as bop:
        # identity residue
        bop.drop_column("batch_code")

        # triple-truth snapshots
        bop.drop_column("item_name")
        bop.drop_column("item_sku")
        bop.drop_column("category")
        bop.drop_column("spec_text")
        bop.drop_column("base_uom")
        bop.drop_column("purchase_uom")
        bop.drop_column("barcode")


def downgrade() -> None:
    with op.batch_alter_table("inbound_receipt_lines") as bop:
        bop.add_column(sa.Column("batch_code", sa.String(length=64), nullable=True))

        bop.add_column(sa.Column("item_name", sa.String(length=255), nullable=True))
        bop.add_column(sa.Column("item_sku", sa.String(length=64), nullable=True))
        bop.add_column(sa.Column("category", sa.String(length=64), nullable=True))
        bop.add_column(sa.Column("spec_text", sa.String(length=255), nullable=True))
        bop.add_column(sa.Column("base_uom", sa.String(length=32), nullable=True))
        bop.add_column(sa.Column("purchase_uom", sa.String(length=32), nullable=True))
        bop.add_column(sa.Column("barcode", sa.String(length=128), nullable=True))

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_inbound_receipt_lines_item_batch "
        "ON public.inbound_receipt_lines USING btree (item_id, batch_code)"
    )
