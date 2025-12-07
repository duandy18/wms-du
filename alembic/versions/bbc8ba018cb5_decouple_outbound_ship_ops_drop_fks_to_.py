"""decouple outbound_ship_ops: drop FKs to items/locations

Revision ID: bbc8ba018cb5
Revises: b3c92cd33ad4
Create Date: 2025-11-07 11:45:09.433373
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# --- Alembic identifiers ---
revision: str = "bbc8ba018cb5"
down_revision: Union[str, Sequence[str], None] = "b3c92cd33ad4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "outbound_ship_ops"
_FK_ITEM = "outbound_ship_ops_item_id_fkey"
_FK_LOC = "outbound_ship_ops_location_id_fkey"


def _fk_exists(insp: sa.engine.reflection.Inspector, table: str, fk_name: str) -> bool:
    """检测给定表是否存在指定名称的外键。"""
    for fk in insp.get_foreign_keys(table):
        if fk.get("name") == fk_name:
            return True
    return False


def upgrade() -> None:
    """移除 outbound_ship_ops -> items/locations 外键，保持幂等表轻耦合。"""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 若表不存在则直接返回
    if not insp.has_table(_TABLE):
        return

    # 安全删除外键（若存在）
    if _fk_exists(insp, _TABLE, _FK_ITEM):
        op.drop_constraint(_FK_ITEM, _TABLE, type_="foreignkey")
    if _fk_exists(insp, _TABLE, _FK_LOC):
        op.drop_constraint(_FK_LOC, _TABLE, type_="foreignkey")


def downgrade() -> None:
    """恢复原外键（若已不存在则创建）。"""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table(_TABLE):
        return

    # 恢复外键
    if not _fk_exists(insp, _TABLE, _FK_ITEM):
        op.create_foreign_key(
            _FK_ITEM,
            _TABLE,
            "items",
            local_cols=["item_id"],
            remote_cols=["id"],
            ondelete="RESTRICT",
        )
    if not _fk_exists(insp, _TABLE, _FK_LOC):
        op.create_foreign_key(
            _FK_LOC,
            _TABLE,
            "locations",
            local_cols=["location_id"],
            remote_cols=["id"],
            ondelete="RESTRICT",
        )
