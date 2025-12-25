"""suppliers_code_not_null

Revision ID: 7c1063ea1d78
Revises: a8fa05588df5
Create Date: 2025-12-13 10:39:30.295756

目标（Phase 3 延展）：
- suppliers.code 成为“稳定引用编码”，不得为空
- 对历史 NULL/空字符串 code 做一次性回填
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7c1063ea1d78"
down_revision: Union[str, Sequence[str], None] = "a8fa05588df5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    升级策略：
    1) 回填历史 suppliers.code：NULL / 空字符串 → SUP-<id>
       - 使用主键 id 构造，天然唯一、稳定、可追溯
       - 避免引入序列/随机数导致不可解释
    2) 将 suppliers.code 改为 NOT NULL
    """
    # 1) 回填 NULL/空字符串 code
    op.execute(
        sa.text(
            """
            UPDATE suppliers
               SET code = 'SUP-' || id::text
             WHERE code IS NULL OR btrim(code) = '';
            """
        )
    )

    # 2) 改为 NOT NULL
    op.alter_column(
        "suppliers",
        "code",
        existing_type=sa.String(length=64),
        nullable=False,
    )


def downgrade() -> None:
    """
    回滚策略：
    - 仅放开 NOT NULL 约束（不回滚回填的数据，避免数据损失）
    """
    op.alter_column(
        "suppliers",
        "code",
        existing_type=sa.String(length=64),
        nullable=True,
    )
