"""phase_m3 lots snapshot migrate to item_uoms triple

Revision ID: 7a3ef051ec9a
Revises: a4bcb4173ca4
Create Date: 2026-02-28 19:15:50.644250

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7a3ef051ec9a"
down_revision: Union[str, Sequence[str], None] = "a4bcb4173ca4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    数据迁移（Phase M-3）：
    - lots 的包装/单位快照解释器统一以 item_uoms（purchase_default）为真相源回填
    - 目的：彻底切断对 items.case_ratio/case_uom 的依赖（后续将删除 items.case_*）
    - 当前采用“就地纠偏”策略：仍使用既有 lots 字段
      * item_uom_snapshot：若为空，回填 items.uom（base_uom）
      * item_case_ratio_snapshot / item_case_uom_snapshot：由 purchase_default 的 ratio_to_base / display_name 推导
        - ratio_to_base <= 1 => 两者置 NULL（表示按 base 输入）
        - ratio_to_base >  1 => 写入 ratio + display_name（display_name 为空则回退 uom）
    """
    op.execute(
        sa.text(
            """
            UPDATE lots l
               SET
                 item_uom_snapshot = COALESCE(l.item_uom_snapshot, i.uom),
                 item_case_ratio_snapshot = CASE
                     WHEN u.ratio_to_base > 1 THEN u.ratio_to_base
                     ELSE NULL
                 END,
                 item_case_uom_snapshot = CASE
                     WHEN u.ratio_to_base > 1 THEN COALESCE(NULLIF(u.display_name,''), u.uom)
                     ELSE NULL
                 END
              FROM items i
              JOIN item_uoms u
                ON u.item_id = i.id
               AND u.is_purchase_default = true
             WHERE l.item_id = i.id
            """
        )
    )


def downgrade() -> None:
    """
    数据迁移不可逆：
    - 回填是“纠偏 + 规范化”，回滚会导致历史 lot 解释链丢失，不做自动反向。
    - schema 回滚由其它 revision 负责；此处保持 no-op。
    """
    pass
