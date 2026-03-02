"""phase3: enforce inbound_receipt_lines.lot_id not null and decouple lots from code/source

Revision ID: 1932b2dafbf8
Revises: 74d50824066e
Create Date: 2026-02-27 21:46:52.869036
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1932b2dafbf8"
down_revision: Union[str, Sequence[str], None] = "74d50824066e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase 3 DB hardening:

    1) inbound_receipt_lines.lot_id 强制 NOT NULL
       —— 入库提交必须生成 lot_id（由应用层保证）

    2) 解除 lots 表对 lot_code/source 的强耦合 CHECK
       —— lot_id 为槽位身份，不再依赖 lot_code_source 语义

    3) lot_code 仅作为展示字段：
       —— 有值时保证同仓同品唯一；无值不约束
    """

    # 1) 强制入库行必须有 lot_id
    op.execute(
        """
        ALTER TABLE inbound_receipt_lines
        ALTER COLUMN lot_id SET NOT NULL;
        """
    )

    # 2) 删除会制造“来源决定 lot 存在方式”误解的 CHECK
    op.execute(
        """
        ALTER TABLE lots
        DROP CONSTRAINT IF EXISTS ck_lots_internal_requires_source;
        """
    )

    op.execute(
        """
        ALTER TABLE lots
        DROP CONSTRAINT IF EXISTS ck_lots_supplier_requires_lot_code_and_no_source;
        """
    )

    # 3) lot_code 仅作为展示唯一（可选）
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_lots_wh_item_lot_code
        ON lots (warehouse_id, item_id, lot_code)
        WHERE lot_code IS NOT NULL;
        """
    )


def downgrade() -> None:
    """
    回滚说明：

    - 恢复 inbound_receipt_lines.lot_id 可空
    - 删除 lot_code 展示唯一索引
    - 不自动恢复旧 CHECK（避免重新引入语义耦合）
    """

    # 1) 允许 lot_id 可空（回滚）
    op.execute(
        """
        ALTER TABLE inbound_receipt_lines
        ALTER COLUMN lot_id DROP NOT NULL;
        """
    )

    # 2) 删除展示唯一索引
    op.execute(
        """
        DROP INDEX IF EXISTS uq_lots_wh_item_lot_code;
        """
    )

    # ⚠️ 不恢复旧 CHECK，避免再次引入 lot_code/source 强耦合
