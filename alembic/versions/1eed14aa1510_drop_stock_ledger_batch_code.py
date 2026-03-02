"""drop stock_ledger.batch_code

Revision ID: 1eed14aa1510
Revises: 7dbddf699adc
Create Date: 2026-02-28 13:23:01.892293

Phase 3:

- Remove batch_code from stock_ledger.
- Drop related indexes/constraints if present.
- Enforce lot-only identity in ledger layer.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1eed14aa1510"
down_revision: Union[str, Sequence[str], None] = "7dbddf699adc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------
    # 1) Drop indexes/constraints that may reference batch_code
    # ------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS public.ix_stock_ledger_batch_code")
    op.execute("DROP INDEX IF EXISTS public.ix_stock_ledger_batch_code_key")
    op.execute("DROP INDEX IF EXISTS public.uq_ledger_ref_item_wh_batch_neg")

    # ------------------------------------------------------------
    # 2) Drop column batch_code
    # ------------------------------------------------------------
    with op.batch_alter_table("stock_ledger") as bop:
        bop.drop_column("batch_code")


def downgrade() -> None:
    # ------------------------------------------------------------
    # 1) Restore column
    # ------------------------------------------------------------
    with op.batch_alter_table("stock_ledger") as bop:
        bop.add_column(
            sa.Column("batch_code", sa.String(length=64), nullable=True)
        )

    # ------------------------------------------------------------
    # 2) Restore a basic index (best-effort)
    # ------------------------------------------------------------
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_stock_ledger_batch_code "
        "ON public.stock_ledger USING btree (batch_code)"
    )
