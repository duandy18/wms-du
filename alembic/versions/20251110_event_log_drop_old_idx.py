"""event_log: drop legacy indexes

Revision ID: 20251110_event_log_drop_old_idx
Revises: 20251110_orders_drop_legacy
Create Date: 2025-11-09 13:20:00
"""

from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251110_event_log_drop_old_idx"
down_revision: Union[str, Sequence[str], None] = "20251110_orders_drop_legacy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    清理 event_log 上已废弃的旧索引（全部幂等）。
    注意：若线上仍依赖这些索引，请在迁移前确认替代方案。
    """
    op.execute("DROP INDEX IF EXISTS ix_event_log_message_gin;")
    op.execute("DROP INDEX IF EXISTS ix_event_log_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_event_log_occurred_at;")
    op.execute("DROP INDEX IF EXISTS ix_event_log_level;")


def downgrade() -> None:
    """
    回滚时保守重建基础 BTree 索引（不恢复 GIN 版本的定义，避免误导）。
    如确需恢复历史 GIN/表达式索引，请基于当年的 DDL 单独补。
    """
    op.execute("CREATE INDEX IF NOT EXISTS ix_event_log_level ON event_log(level);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_event_log_created_at ON event_log(created_at);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_event_log_occurred_at ON event_log(occurred_at);")
    # GIN 索引历史定义未知，出于安全不在此处恢复
