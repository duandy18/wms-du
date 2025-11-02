"""fix fefo index on batches: (item_id, location_id, expiry_date, id)

Revision ID: 20251028_fix_fefo_index_on_batches
Revises: 20251028_event_error_pending_view
Create Date: 2025-10-28 13:20:00
"""
from alembic import op
import sqlalchemy as sa

revision = "20251028_fix_fefo_index_on_batches"
down_revision = "20251028_event_error_pending_view"
branch_labels = None
depends_on = None

IDX = "ix_batches_fefo"

def _idx_def(conn, name):
    row = conn.execute(sa.text("""
        SELECT indexdef FROM pg_indexes
        WHERE schemaname='public' AND indexname=:n
    """), {"n": name}).scalar()
    return row or ""

def upgrade():
    conn = op.get_bind()
    cur = _idx_def(conn, IDX)
    # 不是我们期望的定义就重建
    want = "USING btree (item_id, location_id, expiry_date, id)"
    if want not in cur:
        op.execute(f"DROP INDEX IF EXISTS {IDX}")
        op.execute(f"CREATE INDEX {IDX} ON public.batches USING btree (item_id, location_id, expiry_date, id)")
        op.execute("ANALYZE public.batches")

def downgrade():
    # 回滚为较宽松的 (item_id, expiry_date)
    op.execute(f"DROP INDEX IF EXISTS {IDX}")
    op.execute(f"CREATE INDEX {IDX} ON public.batches USING btree (item_id, expiry_date)")
