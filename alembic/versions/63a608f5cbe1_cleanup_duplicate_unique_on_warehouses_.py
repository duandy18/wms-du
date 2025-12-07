"""cleanup_duplicate_unique_on_warehouses_name

Revision ID: 63a608f5cbe1
Revises: 940f162efefa
Create Date: 2025-11-27 08:05:09.460552

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "63a608f5cbe1"
down_revision: Union[str, Sequence[str], None] = "940f162efefa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    清理 warehouses.name 上重复的唯一约束 / 索引。

    现状（psql \d warehouses）：
      - ix_warehouses_name_uq  UNIQUE, btree (name)
      - uq_warehouses_name     UNIQUE, btree (name)

    目标：
      - 删除 ix_warehouses_name_uq
      - 保留 uq_warehouses_name
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # 取出当前索引名
    try:
        index_names = {idx["name"] for idx in insp.get_indexes("warehouses")}
    except Exception:
        index_names = set()

    # 删除多余的 unique index
    if "ix_warehouses_name_uq" in index_names:
        op.drop_index("ix_warehouses_name_uq", table_name="warehouses")


def downgrade() -> None:
    """
    回滚：重新创建 ix_warehouses_name_uq 唯一索引。

    注意：仍然会与 uq_warehouses_name 重叠，但这是 downgrade 的预期。
    """
    op.create_index(
        "ix_warehouses_name_uq",
        "warehouses",
        ["name"],
        unique=True,
    )
