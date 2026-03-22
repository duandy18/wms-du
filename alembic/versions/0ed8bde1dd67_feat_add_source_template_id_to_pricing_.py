"""feat: add source_template_id to pricing_templates and cloned structure lock

Revision ID: 0ed8bde1dd67
Revises: 00100b843946
Create Date: 2026-03-22 21:17:46.077715
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0ed8bde1dd67"
down_revision: Union[str, Sequence[str], None] = "00100b843946"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 新增字段
    op.add_column(
        "shipping_provider_pricing_templates",
        sa.Column(
            "source_template_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    # 2) 自引用 FK
    op.create_foreign_key(
        "fk_sppt_source_template_id",
        "shipping_provider_pricing_templates",
        "shipping_provider_pricing_templates",
        ["source_template_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3) index（保持和现有风格一致）
    op.create_index(
        "ix_shipping_provider_pricing_templates_source_template_id",
        "shipping_provider_pricing_templates",
        ["source_template_id"],
    )


def downgrade() -> None:
    # 反向删除（顺序必须反过来）

    op.drop_index(
        "ix_shipping_provider_pricing_templates_source_template_id",
        table_name="shipping_provider_pricing_templates",
    )

    op.drop_constraint(
        "fk_sppt_source_template_id",
        "shipping_provider_pricing_templates",
        type_="foreignkey",
    )

    op.drop_column(
        "shipping_provider_pricing_templates",
        "source_template_id",
    )
