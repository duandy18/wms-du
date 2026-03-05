"""dedupe items supplier fk

- Drop legacy duplicate FK: fk_items_supplier_id_suppliers (ON DELETE SET NULL)
- Ensure canonical FK: fk_items_supplier (ON DELETE RESTRICT)

Revision ID: 8a6e7c773be0
Revises: dd0aecff83e0
Create Date: 2026-02-06 11:30:54.265880
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "8a6e7c773be0"
down_revision: Union[str, Sequence[str], None] = "dd0aecff83e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 删除历史遗留的重复外键（SET NULL 语义，必须清掉）
    op.execute(
        "ALTER TABLE items DROP CONSTRAINT IF EXISTS fk_items_supplier_id_suppliers"
    )

    # 2) 为了保证跨环境确定性：
    #    先 drop 再 create canonical FK（RESTRICT）
    op.drop_constraint(
        "fk_items_supplier",
        "items",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_items_supplier",
        "items",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # 回滚策略：恢复为 SET NULL（如果你们将来绝不回滚，也可以简化）
    op.drop_constraint(
        "fk_items_supplier",
        "items",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_items_supplier",
        "items",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_foreign_key(
        "fk_items_supplier_id_suppliers",
        "items",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )
