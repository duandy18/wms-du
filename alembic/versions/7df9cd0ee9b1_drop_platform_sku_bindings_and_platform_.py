"""drop platform_sku_bindings and platform_sku_mirror

Revision ID: 7df9cd0ee9b1
Revises: 9f45181ddee2
Create Date: 2026-02-10 09:31:58.174264

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7df9cd0ee9b1"
down_revision: Union[str, Sequence[str], None] = "9f45181ddee2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    PSKU 治理体系已在代码层完全下线：

    - 不再存在 platform_sku_bindings / platform_sku_mirror 的读写路径
    - 解析主线已切换为：填写码 → FSKU.code → published FSKU
    - PSKU 仅作为历史事实字段名存在（platform_sku_id），不再需要物理表

    本迁移负责物理删除历史表。
    """

    # 显式删除，确保语义清晰
    op.drop_table("platform_sku_bindings")
    op.drop_table("platform_sku_mirror")


def downgrade() -> None:
    """
    不支持回滚。

    PSKU 表属于已废弃业务主线，
    回滚将导致数据库结构与当前代码语义不一致。
    """
    raise RuntimeError(
        "platform_sku_bindings / platform_sku_mirror 已永久废弃，不支持 downgrade"
    )
