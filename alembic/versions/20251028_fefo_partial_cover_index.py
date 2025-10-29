"""fefo partial covering index on batches

Revision ID: 20251028_fefo_partial_cover_index
Revises: 20251028_fix_fefo_index_on_batches
Create Date: 2025-10-28 13:45:00
"""
from alembic import op
import sqlalchemy as sa

revision = "20251028_fefo_partial_cover_index"
down_revision = "20251028_fix_fefo_index_on_batches"
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
    want = "USING btree (item_id, location_id, expiry_date, id) INCLUDE (batch_code, qty) WHERE (qty > 0)"
    if want not in cur:
        op.execute(f"DROP INDEX IF EXISTS {IDX}")
        op.execute(f"""
            CREATE INDEX {IDX}
            ON public.batches USING btree (item_id, location_id, expiry_date, id)
            INCLUDE (batch_code, qty)
            WHERE qty > 0
        """)
        op.execute("ANALYZE public.batches")

def downgrade():
    op.execute(f"DROP INDEX IF EXISTS {IDX}")
    op.execute(f"""
        CREATE INDEX {IDX}
        ON public.batches USING btree (item_id, location_id, expiry_date, id)
    """)
