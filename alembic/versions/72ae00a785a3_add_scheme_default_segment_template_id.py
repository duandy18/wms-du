"""add scheme default_segment_template_id

Revision ID: 72ae00a785a3
Revises: f92578cb0ef4
Create Date: 2026-01-27 21:36:24.354758
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "72ae00a785a3"
down_revision: Union[str, Sequence[str], None] = "f92578cb0ef4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) add column
    op.add_column(
        "shipping_provider_pricing_schemes",
        sa.Column("default_segment_template_id", sa.Integer(), nullable=True),
    )

    # 2) FK（名字也要短）
    op.create_foreign_key(
        "fk_sch_def_seg_tpl",
        "shipping_provider_pricing_schemes",
        "shipping_provider_pricing_scheme_segment_templates",
        ["default_segment_template_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3) index —— ⚠️ 名字必须 < 63 chars
    op.create_index(
        "ix_sch_def_seg_tpl",
        "shipping_provider_pricing_schemes",
        ["default_segment_template_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sch_def_seg_tpl",
        table_name="shipping_provider_pricing_schemes",
    )

    op.drop_constraint(
        "fk_sch_def_seg_tpl",
        "shipping_provider_pricing_schemes",
        type_="foreignkey",
    )

    op.drop_column(
        "shipping_provider_pricing_schemes",
        "default_segment_template_id",
    )
