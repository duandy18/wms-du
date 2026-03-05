"""phase3: drop legacy lots supplier/internal partial unique indexes

Revision ID: 6bd0d6f7cb2a
Revises: 1932b2dafbf8
Create Date: 2026-02-27 21:56:40.240974
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "6bd0d6f7cb2a"
down_revision: Union[str, Sequence[str], None] = "1932b2dafbf8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase 3 清理旧 lots 分支唯一索引：

    删除：
      - uq_lots_supplier_wh_item_lot_code
      - uq_lots_internal_wh_item_source

    保留：
      - uq_lots_wh_item_lot_code（lot_code 有值才唯一）
    """

    op.execute("DROP INDEX IF EXISTS uq_lots_supplier_wh_item_lot_code;")
    op.execute("DROP INDEX IF EXISTS uq_lots_internal_wh_item_source;")


def downgrade() -> None:
    """
    回滚：恢复旧分支索引（仅当你真的需要回到旧语义）
    """

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_lots_supplier_wh_item_lot_code
        ON lots (warehouse_id, item_id, lot_code_source, lot_code)
        WHERE lot_code_source::text = 'SUPPLIER'::text;
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_lots_internal_wh_item_source
        ON lots (warehouse_id, item_id, lot_code_source, source_receipt_id, source_line_no)
        WHERE lot_code_source::text = 'INTERNAL'::text;
        """
    )
