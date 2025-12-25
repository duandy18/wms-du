"""add_segments_json_to_shipping_provider_pricing_schemes

Revision ID: b60b409dedab
Revises: 7ef940d6d5f2
Create Date: 2025-12-23 16:39:18.427166

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b60b409dedab"
down_revision: Union[str, Sequence[str], None] = "7ef940d6d5f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_sqlite(bind) -> bool:
    return (bind.dialect.name or "").lower() == "sqlite"


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    sqlite = _is_sqlite(bind)

    insp = sa.inspect(bind)
    schema = None if sqlite else "public"

    # 表不存在就不做（避免裁剪 scope / 测试环境误炸）
    if "shipping_provider_pricing_schemes" not in insp.get_table_names(schema=schema):
        return

    cols = [c["name"] for c in insp.get_columns("shipping_provider_pricing_schemes", schema=schema)]

    # 1) segments_json：JSONB (sqlite 用 JSON)
    if "segments_json" not in cols:
        col_type = sa.JSON() if sqlite else postgresql.JSONB(astext_type=sa.Text())
        op.add_column(
            "shipping_provider_pricing_schemes",
            sa.Column("segments_json", col_type, nullable=True),
        )

    # 2) segments_updated_at：timestamptz
    if "segments_updated_at" not in cols:
        op.add_column(
            "shipping_provider_pricing_schemes",
            sa.Column("segments_updated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    sqlite = _is_sqlite(bind)

    insp = sa.inspect(bind)
    schema = None if sqlite else "public"

    if "shipping_provider_pricing_schemes" not in insp.get_table_names(schema=schema):
        return

    cols = [c["name"] for c in insp.get_columns("shipping_provider_pricing_schemes", schema=schema)]

    # 先删 updated_at 再删 json（顺序无所谓，但保持一致）
    if "segments_updated_at" in cols:
        op.drop_column("shipping_provider_pricing_schemes", "segments_updated_at")

    if "segments_json" in cols:
        op.drop_column("shipping_provider_pricing_schemes", "segments_json")
