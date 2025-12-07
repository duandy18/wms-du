"""backfill_po_supplier_name_and_total_amount

Revision ID: a655a322bc4f
Revises: ec0eafe4b6d5
Create Date: 2025-11-27 19:51:43.511934

补齐 Phase 2 的头表快照字段：
- supplier_name 为 NULL → 回填为旧字段 supplier 文本
- total_amount 为 NULL → 回填为 qty_ordered * unit_cost

可安全执行，不会影响未来 v2 业务逻辑。
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision: str = "a655a322bc4f"
down_revision: Union[str, Sequence[str], None] = "ec0eafe4b6d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ----------------------------------------------------
    # 1) supplier_name 快照补齐
    # ----------------------------------------------------
    conn.execute(
        text(
            """
            UPDATE purchase_orders
               SET supplier_name = supplier
             WHERE supplier_name IS NULL
            """
        )
    )

    # ----------------------------------------------------
    # 2) total_amount 补齐
    # ----------------------------------------------------
    conn.execute(
        text(
            """
            UPDATE purchase_orders
               SET total_amount = qty_ordered * unit_cost
             WHERE total_amount IS NULL
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    # ----------------------------------------------------
    # 回滚策略（谨慎模式）：
    #
    # 仅在“值由本 migration 填写”的情况下置空：
    # - supplier_name == supplier 才视为本迁移填的；
    # - total_amount == qty_ordered * unit_cost 才视为本迁移填的。
    #
    # 这样避免把未来手工修补或真正业务值误删。
    # ----------------------------------------------------

    conn.execute(
        text(
            """
            UPDATE purchase_orders
               SET supplier_name = NULL
             WHERE supplier_name = supplier
            """
        )
    )

    conn.execute(
        text(
            """
            UPDATE purchase_orders
               SET total_amount = NULL
             WHERE total_amount = qty_ordered * unit_cost
            """
        )
    )
