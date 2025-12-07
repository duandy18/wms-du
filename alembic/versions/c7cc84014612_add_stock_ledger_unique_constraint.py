"""add stock_ledger unique constraint

Revision ID: c7cc84014612
Revises: 154abbe040c3
Create Date: 2025-11-30 11:43:31.681507
"""

from typing import Sequence, Union

from alembic import op  # noqa: F401  保留 import，方便以后需要扩展

# revision identifiers, used by Alembic.
revision = "c7cc84014612"
down_revision = "154abbe040c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema.

    说明：
    - 当前 Postgres 库中已经存在名为
      uq_ledger_wh_batch_item_reason_ref_line 的 UNIQUE 约束；
    - 之前曾尝试在 migration 中重复创建，触发了
      'relation ... already exists' / 'cannot drop index ...' 错误；
    - 因此，这个 migration 现在仅作为“标记用”迁移，不再对 DB 结构做任何修改。

    后果：
    - Alembic 迁移链会正确纪录到 revision=c7cc84014612；
    - DB 端 stock_ledger 上的约束保持现有状态（已存在）。
    """
    pass


def downgrade() -> None:
    """
    Downgrade schema.

    出于安全考虑，这里也不做删除约束的操作，
    保持 downgrade 为 no-op。

    如果未来确实需要移除该约束，可以在新的 migration 中
    明确执行 op.drop_constraint(...)。
    """
    pass
