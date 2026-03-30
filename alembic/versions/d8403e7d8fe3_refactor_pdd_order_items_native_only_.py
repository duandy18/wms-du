"""refactor pdd order items native-only fields

Revision ID: d8403e7d8fe3
Revises: 1393224277ee
Create Date: 2026-03-30 13:45:25.618188

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d8403e7d8fe3"
down_revision: Union[str, Sequence[str], None] = "1393224277ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index("ix_pdd_order_items_sku_code", table_name="pdd_order_items")
    op.drop_index("ix_pdd_order_items_match_status", table_name="pdd_order_items")

    op.drop_constraint(
        "pdd_order_items_matched_binding_id_fkey",
        "pdd_order_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "pdd_order_items_matched_fsku_id_fkey",
        "pdd_order_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "pdd_order_items_matched_item_id_fkey",
        "pdd_order_items",
        type_="foreignkey",
    )

    op.drop_column("pdd_order_items", "sku_code")
    op.drop_column("pdd_order_items", "sku_name")
    op.drop_column("pdd_order_items", "line_amount")
    op.drop_column("pdd_order_items", "match_status")
    op.drop_column("pdd_order_items", "match_reason")
    op.drop_column("pdd_order_items", "matched_item_id")
    op.drop_column("pdd_order_items", "matched_fsku_id")
    op.drop_column("pdd_order_items", "matched_binding_id")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "pdd_order_items",
        sa.Column(
            "matched_binding_id",
            sa.BigInteger(),
            nullable=True,
            comment="命中的 merchant_code_fsku_binding id",
        ),
    )
    op.add_column(
        "pdd_order_items",
        sa.Column(
            "matched_fsku_id",
            sa.BigInteger(),
            nullable=True,
            comment="匹配到的内部 fsku_id",
        ),
    )
    op.add_column(
        "pdd_order_items",
        sa.Column(
            "matched_item_id",
            sa.Integer(),
            nullable=True,
            comment="匹配到的内部 item_id",
        ),
    )
    op.add_column(
        "pdd_order_items",
        sa.Column(
            "match_reason",
            sa.String(length=255),
            nullable=True,
            comment="商品匹配结果原因摘要",
        ),
    )
    op.add_column(
        "pdd_order_items",
        sa.Column(
            "match_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="商品匹配状态：pending / matched / multiple_candidates / not_found / invalid_code",
        ),
    )
    op.add_column(
        "pdd_order_items",
        sa.Column(
            "line_amount",
            sa.Numeric(14, 2),
            nullable=True,
            comment="行金额（元）",
        ),
    )
    op.add_column(
        "pdd_order_items",
        sa.Column(
            "sku_name",
            sa.String(length=255),
            nullable=True,
            comment="平台规格名",
        ),
    )
    op.add_column(
        "pdd_order_items",
        sa.Column(
            "sku_code",
            sa.String(length=128),
            nullable=True,
            comment="归一后的 sku_code（通常来自 outer_id）",
        ),
    )

    op.create_foreign_key(
        "pdd_order_items_matched_item_id_fkey",
        "pdd_order_items",
        "items",
        ["matched_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "pdd_order_items_matched_fsku_id_fkey",
        "pdd_order_items",
        "fskus",
        ["matched_fsku_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "pdd_order_items_matched_binding_id_fkey",
        "pdd_order_items",
        "merchant_code_fsku_bindings",
        ["matched_binding_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index("ix_pdd_order_items_match_status", "pdd_order_items", ["match_status"])
    op.create_index("ix_pdd_order_items_sku_code", "pdd_order_items", ["sku_code"])

    op.alter_column(
        "pdd_order_items",
        "match_status",
        server_default=None,
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )
