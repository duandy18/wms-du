"""phase_m3 forbid items.case_ratio_case_uom (must be NULL)

Revision ID: 2c38424c780a
Revises: 7a3ef051ec9a
Create Date: 2026-03-01 01:09:27.203277

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2c38424c780a"
down_revision: Union[str, Sequence[str], None] = "7a3ef051ec9a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CK_NAME = "ck_items_case_fields_must_be_null"


def upgrade() -> None:
    """
    Phase M-3：
    - items.case_ratio / case_uom 已结构性废弃
    - 在删除列前，先通过 CHECK 约束封死写入口（必须为 NULL）
    """

    # 防御性清理：如果历史数据里存在非 NULL，统一归零为 NULL
    op.execute(
        sa.text(
            """
            UPDATE items
               SET case_ratio = NULL,
                   case_uom   = NULL
             WHERE case_ratio IS NOT NULL
                OR case_uom   IS NOT NULL
            """
        )
    )

    # 新增 CHECK 约束：禁止未来写入
    op.create_check_constraint(
        CK_NAME,
        "items",
        "case_ratio IS NULL AND case_uom IS NULL",
    )


def downgrade() -> None:
    """
    回滚：
    - 移除 CHECK 约束（允许再次写入 case_*）
    - 不恢复历史值（数据已被清空）
    """
    op.drop_constraint(CK_NAME, "items", type_="check")
