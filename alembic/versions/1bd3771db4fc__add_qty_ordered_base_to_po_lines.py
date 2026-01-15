"""schema: add qty_ordered_base to purchase_order_lines and backfill

Revision ID: 1bd3771db4fc
Revises: 2bb34905ead3
Create Date: 2026-01-14 16:57:11.415898

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1bd3771db4fc"
down_revision: Union[str, Sequence[str], None] = "2bb34905ead3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 新增列：先 nullable=True，便于回填
    op.add_column(
        "purchase_order_lines",
        sa.Column(
            "qty_ordered_base",
            sa.Integer(),
            nullable=True,
            comment="订购数量（最小单位，事实字段）",
        ),
    )

    # 2) 回填历史数据（只填 NULL，避免重复乘）
    bind.execute(
        sa.text(
            """
            UPDATE purchase_order_lines
               SET qty_ordered_base =
                 COALESCE(qty_ordered, 0) * COALESCE(NULLIF(units_per_case, 0), 1)
             WHERE qty_ordered_base IS NULL
            """
        )
    )

    # 3) 设默认值 + NOT NULL
    bind.execute(
        sa.text(
            """
            ALTER TABLE purchase_order_lines
            ALTER COLUMN qty_ordered_base SET DEFAULT 0
            """
        )
    )
    op.alter_column("purchase_order_lines", "qty_ordered_base", nullable=False)

    # 4) 索引（可选但很实用：po_id + ordered_base）
    op.create_index(
        "ix_purchase_order_lines_po_id_qty_ordered_base",
        "purchase_order_lines",
        ["po_id", "qty_ordered_base"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_purchase_order_lines_po_id_qty_ordered_base",
        table_name="purchase_order_lines",
    )
    op.drop_column("purchase_order_lines", "qty_ordered_base")
