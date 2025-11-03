"""event_log.message -> JSONB (idempotent head)

Revision ID: ed9ef423378f
Revises: 7f3b9a2c4d10
Create Date: 2025-11-03 17:58:34.294817
"""
from __future__ import annotations

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision: str = "ed9ef423378f"
down_revision: Union[str, Sequence[str], None] = "7f3b9a2c4d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    该迁移在前置迁移已完成 TEXT->JSONB 的前提下幂等执行：
    - 若需要，可在此处创建 JSONB 索引，或做后续 JSON 结构演进。
    """
    bind: Connection = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # 可选：创建 JSONB GIN 索引（若你需要按 message 字段里的 key/value 检索）
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_event_log_message_gin "
        "ON public.event_log USING gin ((message));"
    )


def downgrade() -> None:
    """回滚 head 中的增量变更（不回滚上游的类型变更）。"""
    bind: Connection = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # 回退可选索引
    op.execute("DROP INDEX IF EXISTS public.ix_event_log_message_gin;")
