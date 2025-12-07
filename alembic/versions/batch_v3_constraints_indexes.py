"""Batch v3 constraints and indexes

- Add CHECK constraint: expiry_date >= production_date
- Add composite indexes for FEFO and batch lookups
"""

from alembic import op
import sqlalchemy as sa

revision = "batch_v3_constraints_indexes"
down_revision = "f15351377fef"
branch_labels = None
depends_on = None


def upgrade():
    # 日期合法性检查
    op.create_check_constraint(
        "ck_batches_valid_dates",
        "batches",
        "(expiry_date IS NULL OR production_date IS NULL OR expiry_date >= production_date)",
    )

    # FEFO / lookup 索引
    op.create_index(
        "ix_batches_wh_item_code",
        "batches",
        ["warehouse_id", "item_id", "batch_code"],
        unique=False,
    )

    op.create_index(
        "ix_batches_wh_item_expiry",
        "batches",
        ["warehouse_id", "item_id", "expiry_date"],
        unique=False,
    )


def downgrade():
    op.drop_constraint("ck_batches_valid_dates", "batches", type_="check")
    op.drop_index("ix_batches_wh_item_code", table_name="batches")
    op.drop_index("ix_batches_wh_item_expiry", table_name="batches")
