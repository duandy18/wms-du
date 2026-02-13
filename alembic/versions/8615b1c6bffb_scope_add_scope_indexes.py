"""scope: add scope indexes

Revision ID: 8615b1c6bffb
Revises: 8f8267bb3fdb
Create Date: 2026-02-13 11:00:45.336309
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8615b1c6bffb"
down_revision: Union[str, Sequence[str], None] = "8f8267bb3fdb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    只补 ORM 期望的 scope 单列索引。

    ⚠️ 注意：某些环境里这些索引可能已经由上一条迁移或手工创建存在。
    因此这里必须幂等（IF NOT EXISTS），避免 DuplicateTable。
    """
    op.execute("CREATE INDEX IF NOT EXISTS ix_stock_ledger_scope ON stock_ledger (scope);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_stocks_scope ON stocks (scope);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_stock_snapshots_scope ON stock_snapshots (scope);")


def downgrade() -> None:
    # 同理：幂等 drop，避免环境差异导致回滚失败
    op.execute("DROP INDEX IF EXISTS ix_stock_snapshots_scope;")
    op.execute("DROP INDEX IF EXISTS ix_stocks_scope;")
    op.execute("DROP INDEX IF EXISTS ix_stock_ledger_scope;")
