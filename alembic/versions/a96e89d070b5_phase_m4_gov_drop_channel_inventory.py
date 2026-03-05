"""phase m4 gov: drop channel_inventory

Revision ID: a96e89d070b5
Revises: 5a34cd869461
Create Date: 2026-03-01 14:46:10.499804

治理阶段：删除渠道库存镜像（channel_inventory）概念。
运行期无引用，仅残留模型与测试 truncate 逻辑；现在统一收口为“仓库/lot-world 单一真相源”。

设计：
- CI-safe / 幂等：IF EXISTS
- downgrade 不支持（治理清理避免误复活）
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a96e89d070b5"
down_revision: Union[str, Sequence[str], None] = "5a34cd869461"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # table + sequence 一并清理；CASCADE 会顺手清索引/约束/FK
    op.execute("DROP TABLE IF EXISTS public.channel_inventory CASCADE;")
    op.execute("DROP SEQUENCE IF EXISTS public.channel_inventory_id_seq CASCADE;")


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade not supported: channel_inventory removed in Phase M-4 governance."
    )
