"""Add production_date & expiry_date to stock_ledger"""

from alembic import op
import sqlalchemy as sa

revision = "ledger_add_batch_dates"
down_revision = "batch_v3_constraints_indexes"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("stock_ledger") as batch:
        batch.add_column(sa.Column("production_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("expiry_date", sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table("stock_ledger") as batch:
        batch.drop_column("production_date")
        batch.drop_column("expiry_date")
