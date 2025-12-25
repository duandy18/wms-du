"""add_bracket_structured_pricing_columns

Revision ID: 0093b5cac184
Revises: eb0977f2d5e7
Create Date: 2025-12-14 12:54:05.750147

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0093b5cac184"
down_revision: Union[str, Sequence[str], None] = "eb0977f2d5e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_zone_brackets"
IDX = "ix_sp_zone_brackets_zone_id_minmax"


def upgrade() -> None:
    # Phase 4: 结构化计价字段（先全部 nullable，保证平滑升级；旧 price_json 仍保留兼容）
    op.add_column(TABLE, sa.Column("pricing_mode", sa.String(length=32), nullable=True))
    op.add_column(TABLE, sa.Column("flat_amount", sa.Numeric(12, 2), nullable=True))

    # 首重/续重模型：amount = base_amount + max(0, w - base_kg) * rate_per_kg
    op.add_column(TABLE, sa.Column("base_kg", sa.Numeric(10, 3), nullable=True))
    op.add_column(TABLE, sa.Column("base_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column(TABLE, sa.Column("rate_per_kg", sa.Numeric(12, 4), nullable=True))

    # Bracket 可覆盖 Scheme 的 rounding（可选）
    op.add_column(TABLE, sa.Column("rounding_mode", sa.String(length=16), nullable=True))
    op.add_column(TABLE, sa.Column("rounding_step_kg", sa.Numeric(10, 3), nullable=True))

    # 可选：常用查询/诊断索引（不改行为，纯加速）
    op.create_index(IDX, TABLE, ["zone_id", "min_kg", "max_kg"])


def downgrade() -> None:
    op.drop_index(IDX, table_name=TABLE)

    op.drop_column(TABLE, "rounding_step_kg")
    op.drop_column(TABLE, "rounding_mode")
    op.drop_column(TABLE, "rate_per_kg")
    op.drop_column(TABLE, "base_amount")
    op.drop_column(TABLE, "base_kg")
    op.drop_column(TABLE, "flat_amount")
    op.drop_column(TABLE, "pricing_mode")
