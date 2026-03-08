"""drop_segments_and_templates

Revision ID: cbd71bffa819
Revises: 06bed84c1140
Create Date: 2026-03-08

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "cbd71bffa819"
down_revision: Union[str, Sequence[str], None] = "06bed84c1140"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase-2：彻底删除旧 segment / template 架构
    """

    bind = op.get_bind()
    insp = inspect(bind)
    schema = None

    # -------------------------
    # 1 删除 scheme 表旧字段
    # -------------------------

    cols = {c["name"] for c in insp.get_columns("shipping_provider_pricing_schemes", schema=schema)}

    with op.batch_alter_table("shipping_provider_pricing_schemes") as batch:

        if "segments_json" in cols:
            batch.drop_column("segments_json")

        if "segments_updated_at" in cols:
            batch.drop_column("segments_updated_at")

    # -------------------------
    # 2 删除旧 segments 表
    # -------------------------

    tables = set(insp.get_table_names(schema=schema))

    if "shipping_provider_pricing_scheme_segments" in tables:
        op.drop_table("shipping_provider_pricing_scheme_segments")

    # -------------------------
    # 3 删除 template 表
    # -------------------------

    if "shipping_provider_pricing_scheme_segment_template_items" in tables:
        op.drop_table("shipping_provider_pricing_scheme_segment_template_items")

    if "shipping_provider_pricing_scheme_segment_templates" in tables:
        op.drop_table("shipping_provider_pricing_scheme_segment_templates")


def downgrade() -> None:
    """
    不允许回退
    """

    raise RuntimeError(
        "Irreversible migration: segment/template architecture permanently removed."
    )
