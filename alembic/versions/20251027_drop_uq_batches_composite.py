"""drop redundant unique (item_id, warehouse_id, location_id, batch_code, production_date, expiry_date)"""

from alembic import op

revision = "20251027_drop_uq_batches_composite"
down_revision = "20251027_drop_legacy_uq_item_batch"  # 按你实际上一条迁移改
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "uq_batches_composite",
        table_name="batches",
        type_="unique",
    )


def downgrade():
    op.create_unique_constraint(
        "uq_batches_composite",
        "batches",
        ["item_id", "warehouse_id", "location_id", "batch_code", "production_date", "expiry_date"],
    )
