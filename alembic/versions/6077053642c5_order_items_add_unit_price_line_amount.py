"""order_items add unit_price & line_amount

Revision ID: 6077053642c5
Revises: 463565ce21db
Create Date: 2025-10-29 16:45:00
"""

from alembic import op
import sqlalchemy as sa

# 保持 revision / down_revision 与实际一致
revision = "6077053642c5"
down_revision = "463565ce21db"
branch_labels = None
depends_on = None


def upgrade():
    # 1) 新增列（先给默认值，保证 NOT NULL 能落地）
    op.add_column(
        "order_items",
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False, server_default="0"),
        schema="public",
    )
    op.add_column(
        "order_items",
        sa.Column("line_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        schema="public",
    )

    # 2) 非负约束（幂等）
    conn = op.get_bind()
    existing_checks = {
        r[0]
        for r in conn.execute(
            sa.text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'public.order_items'::regclass AND contype = 'c'"
            )
        )
    }
    if "ck_order_items_qty_nonneg" not in existing_checks:
        op.create_check_constraint(
            "ck_order_items_qty_nonneg", "order_items", "qty >= 0", schema="public"
        )
    if "ck_order_items_unit_price_nonneg" not in existing_checks:
        op.create_check_constraint(
            "ck_order_items_unit_price_nonneg", "order_items", "unit_price >= 0", schema="public"
        )
    if "ck_order_items_line_amount_nonneg" not in existing_checks:
        op.create_check_constraint(
            "ck_order_items_line_amount_nonneg", "order_items", "line_amount >= 0", schema="public"
        )

    # 3) 可选：如果已有数据，可做一次回填 line_amount = qty * unit_price
    conn.execute(
        sa.text(
            "UPDATE public.order_items SET line_amount = qty * unit_price "
            "WHERE line_amount IS NOT NULL"
        )
    )

    # 4) 去掉默认值，保持模型一致
    op.alter_column("order_items", "unit_price", server_default=None, schema="public")
    op.alter_column("order_items", "line_amount", server_default=None, schema="public")


def downgrade():
    with op.batch_alter_table("order_items", schema="public") as batch:
        batch.drop_constraint("ck_order_items_line_amount_nonneg", type_="check")
        batch.drop_constraint("ck_order_items_unit_price_nonneg", type_="check")
        batch.drop_constraint("ck_order_items_qty_nonneg", type_="check")
        batch.drop_column("line_amount")
        batch.drop_column("unit_price")
