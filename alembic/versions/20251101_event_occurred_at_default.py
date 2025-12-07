"""event_log: set default for occurred_at (compat); same for event_error_log

Revision ID: 20251101_event_occurred_at_default
Revises: 29ee69c580ea
Create Date: 2025-11-01 23:59:00
"""

from alembic import op

revision = "20251101_event_occurred_at_default"
down_revision = "29ee69c580ea"
branch_labels = None
depends_on = None


def upgrade():
    # 兼容老路径：没显式赋值时用 now()
    op.execute("ALTER TABLE event_log ALTER COLUMN occurred_at SET DEFAULT now();")
    op.execute("ALTER TABLE event_error_log ALTER COLUMN occurred_at SET DEFAULT now();")


def downgrade():
    # 回滚：去掉默认值（保留 NOT NULL 口径）
    op.execute("ALTER TABLE event_log ALTER COLUMN occurred_at DROP DEFAULT;")
    op.execute("ALTER TABLE event_error_log ALTER COLUMN occurred_at DROP DEFAULT;")
