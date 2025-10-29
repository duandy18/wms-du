"""event_error_log pending view

Revision ID: 20251028_event_error_pending_view
Revises: 20251028_ledger_uq_deferrable
Create Date: 2025-10-28 12:07:00
"""
from alembic import op
import sqlalchemy as sa

revision = "20251028_event_error_pending_view"
down_revision = "20251028_ledger_uq_deferrable"
branch_labels = None
depends_on = None

VIEW = "v_event_errors_pending"

def _view_exists(conn, name):
    return bool(conn.execute(sa.text("""
        SELECT 1 FROM pg_catalog.pg_views WHERE viewname=:n
        UNION ALL
        SELECT 1 FROM pg_catalog.pg_matviews WHERE matviewname=:n
        LIMIT 1
    """), {"n": name}).scalar())

def upgrade():
    conn = op.get_bind()
    if _view_exists(conn, VIEW):
        op.execute(f'DROP VIEW {VIEW}')
    op.execute(f"""
        CREATE VIEW {VIEW} AS
        SELECT *
        FROM event_error_log
        WHERE retry_count < max_retries
          AND (next_retry_at IS NULL OR next_retry_at <= now())
    """)

def downgrade():
    conn = op.get_bind()
    if _view_exists(conn, VIEW):
        op.execute(f"DROP VIEW {VIEW}")
