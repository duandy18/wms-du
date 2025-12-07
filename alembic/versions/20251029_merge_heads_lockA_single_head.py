# alembic/versions/20251029_merge_heads_lockA_single_head.py
from alembic import op  # noqa

revision = "20251029_merge_heads_lockA_single_head"
down_revision = (
    "20251029_add_warehouse_id_to_stocks",
    "20251029_lock_a_stocks_batch_code",
    "20251029_lockA_add_wh_and_batch_code",
    "20251029_lockA_finalize_schema",
)
branch_labels = None
depends_on = None


def upgrade():
    # Merge migration: no schema changes.
    pass


def downgrade():
    # No split back.
    pass
