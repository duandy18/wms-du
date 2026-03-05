"""po_lines: drop exec+channel cols, add discount, enforce upc/base invariant

Revision ID: d11239f52d9c
Revises: 8d29203d8f7f
Create Date: 2026-02-19 20:20:56.766941
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d11239f52d9c"
down_revision: Union[str, Sequence[str], None] = "8d29203d8f7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --------------------------------------------------
    # 1) 新增折扣字段
    # --------------------------------------------------
    op.add_column(
        "purchase_order_lines",
        sa.Column(
            "discount_amount",
            sa.Numeric(14, 2),
            nullable=False,
            server_default=sa.text("0"),
            comment="整行减免金额（>=0）",
        ),
    )

    op.add_column(
        "purchase_order_lines",
        sa.Column(
            "discount_note",
            sa.Text(),
            nullable=True,
            comment="折扣说明（可选）",
        ),
    )

    # --------------------------------------------------
    # 2) 单位换算方案 A 收敛
    #    units_per_case 设为 NOT NULL default 1
    #    并重算 qty_ordered_base
    # --------------------------------------------------

    op.execute(
        """
        UPDATE purchase_order_lines
           SET units_per_case = 1
         WHERE units_per_case IS NULL
        """
    )

    op.execute(
        """
        UPDATE purchase_order_lines
           SET qty_ordered_base = qty_ordered * units_per_case
        """
    )

    op.alter_column(
        "purchase_order_lines",
        "units_per_case",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("1"),
    )

    # --------------------------------------------------
    # 3) 删除污染/冗余列
    # --------------------------------------------------
    with op.batch_alter_table("purchase_order_lines") as batch_op:
        batch_op.drop_column("qty_received")
        batch_op.drop_column("line_amount")
        batch_op.drop_column("retail_price")
        batch_op.drop_column("promo_price")
        batch_op.drop_column("min_price")
        batch_op.drop_column("qty_cases")
        batch_op.drop_column("category")
        batch_op.drop_column("status")

    # --------------------------------------------------
    # 4) 加强一致性约束
    # --------------------------------------------------
    op.create_check_constraint(
        "ck_po_lines_qty_ordered_positive",
        "purchase_order_lines",
        "qty_ordered > 0",
    )
    op.create_check_constraint(
        "ck_po_lines_units_per_case_positive",
        "purchase_order_lines",
        "units_per_case > 0",
    )
    op.create_check_constraint(
        "ck_po_lines_qty_ordered_base_positive",
        "purchase_order_lines",
        "qty_ordered_base > 0",
    )
    op.create_check_constraint(
        "ck_po_lines_base_eq_ordered_mul_upc",
        "purchase_order_lines",
        "qty_ordered_base = qty_ordered * units_per_case",
    )
    op.create_check_constraint(
        "ck_po_lines_discount_amount_nonneg",
        "purchase_order_lines",
        "discount_amount >= 0",
    )

    # --------------------------------------------------
    # 5) 补齐/统一列注释（修复 alembic-check 的 comment drift）
    # --------------------------------------------------
    op.alter_column(
        "purchase_order_lines",
        "units_per_case",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("1"),
        comment="换算因子：每 1 采购单位包含多少最小单位（>0）",
    )
    op.alter_column(
        "purchase_order_lines",
        "qty_ordered",
        existing_type=sa.Integer(),
        existing_nullable=False,
        comment="订购数量（采购单位口径，>0）",
    )
    op.alter_column(
        "purchase_order_lines",
        "qty_ordered_base",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
        comment="订购数量（最小单位 base，事实字段）",
    )
    op.alter_column(
        "purchase_order_lines",
        "discount_amount",
        existing_type=sa.Numeric(14, 2),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
        comment="整行减免金额（>=0）",
    )


def downgrade() -> None:
    # 1) 删除注释（恢复为旧态：units_per_case/qty_ordered 无 comment；其他回到旧文案）
    op.alter_column(
        "purchase_order_lines",
        "discount_amount",
        existing_type=sa.Numeric(14, 2),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
        comment="整行减免金额（>=0），行金额=qty_ordered_base*supply_price-discount_amount",
    )
    op.alter_column(
        "purchase_order_lines",
        "qty_ordered_base",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
        comment="订购数量（最小单位，事实字段）",
    )
    op.alter_column(
        "purchase_order_lines",
        "qty_ordered",
        existing_type=sa.Integer(),
        existing_nullable=False,
        comment=None,
    )
    op.alter_column(
        "purchase_order_lines",
        "units_per_case",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("1"),
        comment=None,
    )

    # 2) 删除新增约束
    op.drop_constraint("ck_po_lines_discount_amount_nonneg", "purchase_order_lines", type_="check")
    op.drop_constraint("ck_po_lines_base_eq_ordered_mul_upc", "purchase_order_lines", type_="check")
    op.drop_constraint(
        "ck_po_lines_qty_ordered_base_positive", "purchase_order_lines", type_="check"
    )
    op.drop_constraint("ck_po_lines_units_per_case_positive", "purchase_order_lines", type_="check")
    op.drop_constraint("ck_po_lines_qty_ordered_positive", "purchase_order_lines", type_="check")

    # 3) 恢复 units_per_case 可空
    op.alter_column(
        "purchase_order_lines",
        "units_per_case",
        existing_type=sa.Integer(),
        nullable=True,
        server_default=None,
    )

    # 4) 恢复被删除列（回到旧结构）
    with op.batch_alter_table("purchase_order_lines") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status", sa.String(length=32), nullable=False, server_default=sa.text("'CREATED'")
            )
        )
        batch_op.add_column(sa.Column("category", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("qty_cases", sa.Integer(), nullable=True))

        batch_op.add_column(sa.Column("min_price", sa.Numeric(12, 2), nullable=True))
        batch_op.add_column(sa.Column("promo_price", sa.Numeric(12, 2), nullable=True))
        batch_op.add_column(sa.Column("retail_price", sa.Numeric(12, 2), nullable=True))

        batch_op.add_column(sa.Column("line_amount", sa.Numeric(14, 2), nullable=True))
        batch_op.add_column(
            sa.Column("qty_received", sa.Integer(), nullable=False, server_default=sa.text("0"))
        )

    # 5) 删除折扣字段
    op.drop_column("purchase_order_lines", "discount_note")
    op.drop_column("purchase_order_lines", "discount_amount")
