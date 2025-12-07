"""phase_3_7_add_trace_id_to_event_store

Revision ID: a3786a01e11a
Revises: 629edd10564d
Create Date: 2025-11-16 10:14:51.780811
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a3786a01e11a"
down_revision: Union[str, Sequence[str], None] = "629edd10564d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    说明：
    - 部分环境中 event_store.trace_id 可能已经通过手工或其它迁移创建；
    - 这里先检测表是否存在，再使用 IF NOT EXISTS，保证在无表/有表两种情况下都安全。
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 若当前库不存在 event_store，则不做任何操作（v2 线路可以完全没有该表）
    if not insp.has_table("event_store", schema="public"):
        return

    op.execute(
        sa.text(
            """
            ALTER TABLE event_store
            ADD COLUMN IF NOT EXISTS trace_id TEXT
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("event_store", schema="public"):
        return

    op.execute(
        sa.text(
            """
            ALTER TABLE event_store
            DROP COLUMN IF EXISTS trace_id
            """
        )
    )
