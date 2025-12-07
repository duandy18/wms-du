"""Normalize supplier_lot to VARCHAR(128)"""

from alembic import op
import sqlalchemy as sa

revision = "batch_supplier_lot_varchar"
down_revision = "ledger_add_batch_dates"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("batches") as batch:
        batch.alter_column(
            "supplier_lot",
            type_=sa.String(length=128),
            existing_type=sa.Text(),
            nullable=True,
        )


def downgrade():
    with op.batch_alter_table("batches") as batch:
        batch.alter_column(
            "supplier_lot",
            type_=sa.Text(),
            existing_type=sa.String(length=128),
            nullable=True,
        )
