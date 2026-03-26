"""drop_prepare_order_level_provider_fields

Revision ID: cfb8827b7de5
Revises: 43378845be11
Create Date: 2026-03-24 20:31:04.649439

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'cfb8827b7de5'
down_revision: Union[str, Sequence[str], None] = '43378845be11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1. 删除索引（必须先删）
    op.drop_index(
        "ix_order_shipment_prepare_selected_provider_id",
        table_name="order_shipment_prepare",
    )

    # 2. 删除外键
    op.drop_constraint(
        "order_shipment_prepare_selected_provider_id_fkey",
        "order_shipment_prepare",
        type_="foreignkey",
    )

    # 3. 删除列（顺序：先 jsonb，再 fk 列）
    op.drop_column("order_shipment_prepare", "selected_quote_snapshot")
    op.drop_column("order_shipment_prepare", "selected_provider_id")


def downgrade() -> None:
    """Downgrade schema."""

    # 回滚时恢复字段（带 comment，避免 alembic-check 再报）
    op.add_column(
        "order_shipment_prepare",
        sa.Column(
            "selected_provider_id",
            sa.Integer(),
            nullable=True,
            comment="历史遗留字段：订单级已选承运商 shipping_providers.id（不再作为包级真相使用）",
        ),
    )

    op.add_column(
        "order_shipment_prepare",
        sa.Column(
            "selected_quote_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="历史遗留字段：订单级锁定报价快照（不再作为包级真相使用）",
        ),
    )

    op.create_foreign_key(
        "order_shipment_prepare_selected_provider_id_fkey",
        "order_shipment_prepare",
        "shipping_providers",
        ["selected_provider_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_order_shipment_prepare_selected_provider_id",
        "order_shipment_prepare",
        ["selected_provider_id"],
        unique=False,
    )
