"""refactor po lines to snapshot + single fact quantity

Revision ID: e190c49aa0ee
Revises: 6bbf3be91df4
Create Date: 2026-02-21 23:42:02.012590
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e190c49aa0ee"
down_revision: Union[str, Sequence[str], None] = "6bbf3be91df4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------
    # 1️⃣ 新增字段（允许 NULL，后续回填）
    # -------------------------------------------------
    op.add_column(
        "purchase_order_lines",
        sa.Column("uom_snapshot", sa.String(32), nullable=True),
    )
    op.add_column(
        "purchase_order_lines",
        sa.Column("case_ratio_snapshot", sa.Integer(), nullable=True),
    )
    op.add_column(
        "purchase_order_lines",
        sa.Column("case_uom_snapshot", sa.String(16), nullable=True),
    )
    op.add_column(
        "purchase_order_lines",
        sa.Column("qty_ordered_case_input", sa.Integer(), nullable=True),
    )

    # -------------------------------------------------
    # 2️⃣ 回填快照字段
    #
    # 关键修复：
    # - uom_snapshot 来自 items.uom（事实单位快照）
    # - case_ratio_snapshot 对历史行必须取“当时下单真实使用的倍率”= units_per_case
    #   （否则无法保证 qty_ordered_base = qty_ordered_case_input * case_ratio_snapshot）
    # - case_uom_snapshot 优先取 items.case_uom（可空，未治理允许为空）
    # -------------------------------------------------
    op.execute(
        """
        UPDATE purchase_order_lines pol
        SET
            uom_snapshot = i.uom,
            case_ratio_snapshot = CASE
                WHEN pol.units_per_case > 1 THEN pol.units_per_case
                ELSE i.case_ratio
            END,
            case_uom_snapshot = i.case_uom
        FROM items i
        WHERE pol.item_id = i.id
        """
    )

    # -------------------------------------------------
    # 3️⃣ 回填输入痕迹（仅对历史上确实“按箱/按采购口径”录入的行）
    # -------------------------------------------------
    op.execute(
        """
        UPDATE purchase_order_lines
        SET qty_ordered_case_input = qty_ordered
        WHERE units_per_case > 1
        """
    )

    # -------------------------------------------------
    # 4️⃣ 强化约束
    # -------------------------------------------------
    op.alter_column("purchase_order_lines", "uom_snapshot", nullable=False)

    # 输入痕迹存在时，必须可解释
    op.create_check_constraint(
        "ck_po_line_case_input_valid",
        "purchase_order_lines",
        """
        qty_ordered_case_input IS NULL
        OR (
            case_ratio_snapshot IS NOT NULL
            AND qty_ordered_base = qty_ordered_case_input * case_ratio_snapshot
        )
        """,
    )

    # -------------------------------------------------
    # 5️⃣ 删除旧字段（一次性收敛）
    #
    # 注意：先 drop 旧的 check 约束（如果它引用 qty_ordered/units_per_case）
    # -------------------------------------------------
    op.drop_constraint(
        "ck_po_lines_base_eq_ordered_mul_upc",
        "purchase_order_lines",
        type_="check",
    )

    op.drop_column("purchase_order_lines", "purchase_uom")
    op.drop_column("purchase_order_lines", "units_per_case")
    op.drop_column("purchase_order_lines", "qty_ordered")

    # -------------------------------------------------
    # 6️⃣ 强化外键（如果不存在）
    # -------------------------------------------------
    op.create_foreign_key(
        "fk_po_line_item",
        "purchase_order_lines",
        "items",
        ["item_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # -------------------------------------------------
    # 回滚旧结构
    # -------------------------------------------------
    op.drop_constraint("fk_po_line_item", "purchase_order_lines", type_="foreignkey")

    op.add_column(
        "purchase_order_lines",
        sa.Column("qty_ordered", sa.Integer(), nullable=False),
    )
    op.add_column(
        "purchase_order_lines",
        sa.Column("units_per_case", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "purchase_order_lines",
        sa.Column("purchase_uom", sa.String(32), nullable=True),
    )

    # 恢复旧 check（依赖 qty_ordered/units_per_case）
    op.create_check_constraint(
        "ck_po_lines_base_eq_ordered_mul_upc",
        "purchase_order_lines",
        "qty_ordered_base = (qty_ordered * units_per_case)",
    )

    op.drop_constraint("ck_po_line_case_input_valid", "purchase_order_lines", type_="check")

    op.alter_column("purchase_order_lines", "uom_snapshot", nullable=True)

    op.drop_column("purchase_order_lines", "qty_ordered_case_input")
    op.drop_column("purchase_order_lines", "case_uom_snapshot")
    op.drop_column("purchase_order_lines", "case_ratio_snapshot")
    op.drop_column("purchase_order_lines", "uom_snapshot")
