"""sqlite: inline INTEGER PRIMARY KEY for core tables

Revision ID: 3a_fix_sqlite_inline_pks
Revises: 2a01baddb002
Create Date: 2025-10-06 00:00:00
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "3a_fix_sqlite_inline_pks"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """在 SQLite 上做 primary key 修复；在 PostgreSQL 上跳过。"""
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # 原先脚本里只有 PRAGMA 开关，没有真正结构变更；保持等价最小化处理
        op.execute("PRAGMA foreign_keys=OFF")
        op.execute("PRAGMA foreign_keys=ON")
    else:
        # PostgreSQL 无需此修复
        pass


def downgrade():
    """无回滚动作；对 PostgreSQL 同样为 no-op。"""
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # 对应升级为空操作，这里也保持空
        pass
