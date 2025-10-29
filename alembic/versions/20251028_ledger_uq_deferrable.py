"""make ledger UQ deferrable initially deferred

Revision ID: 20251028_ledger_uq_deferrable
Revises: 20251028_batches_add_foreign_keys
Create Date: 2025-10-28 12:05:00
"""
from alembic import op
import sqlalchemy as sa

revision = "20251028_ledger_uq_deferrable"
down_revision = "20251028_batches_add_foreign_keys"
branch_labels = None
depends_on = None

UQ = "uq_ledger_reason_ref_refline_stock"

def _uq_exists(conn, table, name):
    return bool(conn.execute(sa.text("""
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid=c.conrelid
        WHERE t.relname=:t AND c.conname=:n AND c.contype='u' LIMIT 1
    """), {"t": table, "n": name}).scalar())

def upgrade():
    conn = op.get_bind()
    if _uq_exists(conn, "stock_ledger", UQ):
        op.drop_constraint(UQ, "stock_ledger", type_="unique")
    # 以 DEFERRABLE 方式重建
    op.execute(f"""
        ALTER TABLE stock_ledger
        ADD CONSTRAINT {UQ}
        UNIQUE (reason, ref, ref_line, stock_id) DEFERRABLE INITIALLY DEFERRED
    """)

def downgrade():
    conn = op.get_bind()
    if _uq_exists(conn, "stock_ledger", UQ):
        op.drop_constraint(UQ, "stock_ledger", type_="unique")
    op.create_unique_constraint(UQ, "stock_ledger", ["reason","ref","ref_line","stock_id"])
