"""purchase_order_phase2

Revision ID: ec0eafe4b6d5
Revises: c6f9efa91e1b
Create Date: 2025-11-27 19:44:13.544692

Phase 2 内容：
- 扩展 purchase_orders 头表字段：
    supplier_id / supplier_name / total_amount / remark
- 新建 purchase_order_lines 行表（Phase 2 主体）
- 回填旧数据：
    * purchase_orders.supplier_name = supplier
    * purchase_orders.total_amount = qty_ordered * unit_cost
    * 为每条旧 purchase_orders 生成一条行记录（line_no=1）
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func, text


# revision identifiers, used by Alembic.
revision: str = "ec0eafe4b6d5"
down_revision: Union[str, Sequence[str], None] = "c6f9efa91e1b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------
    # 1) 扩展 purchase_orders 头表
    # -----------------------------
    op.add_column(
        "purchase_orders",
        sa.Column("supplier_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "purchase_orders",
        sa.Column("supplier_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "purchase_orders",
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "purchase_orders",
        sa.Column("remark", sa.String(length=255), nullable=True),
    )

    op.create_index(
        "ix_purchase_orders_supplier_id",
        "purchase_orders",
        ["supplier_id"],
    )

    # -----------------------------
    # 2) 创建 purchase_order_lines
    # -----------------------------
    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "po_id",
            sa.Integer(),
            sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(255), nullable=True),
        sa.Column("item_sku", sa.String(64), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("supply_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("retail_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("promo_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("min_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("qty_cases", sa.Integer(), nullable=True),
        sa.Column("units_per_case", sa.Integer(), nullable=True),
        sa.Column("qty_ordered", sa.Integer(), nullable=False),
        sa.Column(
            "qty_received",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("line_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="CREATED",
        ),
        sa.Column("remark", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
        sa.UniqueConstraint(
            "po_id",
            "line_no",
            name="uq_purchase_order_lines_po_id_line_no",
        ),
    )

    op.create_index(
        "ix_purchase_order_lines_po_id",
        "purchase_order_lines",
        ["po_id"],
    )
    op.create_index(
        "ix_purchase_order_lines_item_id",
        "purchase_order_lines",
        ["item_id"],
    )

    # -----------------------------
    # 3) 回填旧数据
    # -----------------------------
    conn = op.get_bind()

    # 3.1 头表 snapshot 字段填充
    conn.execute(
        text(
            """
            UPDATE purchase_orders
               SET supplier_name = supplier_name
                                -- 若为空则填 supplier 文本（老数据）
                                = COALESCE(supplier_name, supplier),
                   total_amount = COALESCE(total_amount, qty_ordered * unit_cost)
            """
        )
    )

    # 3.2 行表：给每条旧 PO 生成一条行记录 (line_no=1)
    conn.execute(
        text(
            """
            INSERT INTO purchase_order_lines (
                po_id,
                line_no,
                item_id,
                item_name,
                item_sku,
                category,
                supply_price,
                retail_price,
                promo_price,
                min_price,
                qty_cases,
                units_per_case,
                qty_ordered,
                qty_received,
                line_amount,
                status,
                remark,
                created_at,
                updated_at
            )
            SELECT
                id          AS po_id,
                1           AS line_no,
                item_id,
                NULL        AS item_name,
                NULL        AS item_sku,
                NULL        AS category,
                unit_cost   AS supply_price,
                NULL        AS retail_price,
                NULL        AS promo_price,
                NULL        AS min_price,
                NULL        AS qty_cases,
                NULL        AS units_per_case,
                qty_ordered,
                qty_received,
                qty_ordered * unit_cost AS line_amount,
                status,
                NULL        AS remark,
                created_at,
                updated_at
            FROM purchase_orders
            """
        )
    )


def downgrade() -> None:
    # 回滚顺序与 upgrade 相反
    op.drop_index("ix_purchase_order_lines_item_id", table_name="purchase_order_lines")
    op.drop_index("ix_purchase_order_lines_po_id", table_name="purchase_order_lines")
    op.drop_table("purchase_order_lines")

    op.drop_index("ix_purchase_orders_supplier_id", table_name="purchase_orders")
    op.drop_column("purchase_orders", "remark")
    op.drop_column("purchase_orders", "total_amount")
    op.drop_column("purchase_orders", "supplier_name")
    op.drop_column("purchase_orders", "supplier_id")
