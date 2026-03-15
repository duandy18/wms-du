"""shipping_records_reconcile_fields_fix

Revision ID: d172eeea2723
Revises: 659e5b5bc318
Create Date: 2026-03-15 18:04:19.318632

说明：
- 该 revision 原本用于修复 shipping_records 对账字段迁移，
  但历史版本中曾错误地重复执行 add_column，导致迁移链冲突。
- 现保留原 revision id 作为桥接迁移（bridge migration），
  兼容已经记录到 d172eeea2723 的数据库环境。
- 实际 schema 变更以 659e5b5bc318 为准，本 revision 不再执行任何 DDL。
"""

from typing import Sequence, Union

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "d172eeea2723"
down_revision: Union[str, Sequence[str], None] = "659e5b5bc318"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Bridge revision: no-op.

    保留该 revision 以维持迁移链连续性；
    不重复执行 shipping_records reconcile 字段相关 DDL。
    """
    pass


def downgrade() -> None:
    """Bridge revision: no-op.

    本 revision 不引入独立 schema 变更，因此回滚时也无需执行任何 DDL。
    """
    pass
