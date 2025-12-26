"""add_pricing_scheme_segments_table

Revision ID: 7ec000d0d03e
Revises: b57f647699f1
Create Date: 2025-12-26 11:19:05.531975

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7ec000d0d03e"
down_revision: Union[str, Sequence[str], None] = "b57f647699f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_sqlite(bind) -> bool:
    return (bind.dialect.name or "").lower() == "sqlite"


def upgrade() -> None:
    bind = op.get_bind()
    sqlite = _is_sqlite(bind)

    insp = sa.inspect(bind)
    schema = None if sqlite else "public"

    # 依赖表不存在就不做（避免测试/裁剪环境误炸）
    if "shipping_provider_pricing_schemes" not in insp.get_table_names(schema=schema):
        return

    # 若已存在则跳过（幂等）
    if "shipping_provider_pricing_scheme_segments" in insp.get_table_names(schema=schema):
        return

    op.create_table(
        "shipping_provider_pricing_scheme_segments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scheme_id", sa.Integer(), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("min_kg", sa.Numeric(10, 3), nullable=False),
        sa.Column("max_kg", sa.Numeric(10, 3), nullable=True),  # NULL = ∞
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["scheme_id"],
            ["shipping_provider_pricing_schemes.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("min_kg >= 0", name="ck_spss_min_kg_nonneg"),
        sa.CheckConstraint("(max_kg IS NULL) OR (max_kg > min_kg)", name="ck_spss_max_gt_min"),
        sa.UniqueConstraint("scheme_id", "ord", name="uq_spss_scheme_ord"),
    )

    op.create_index(
        "ix_spss_scheme_active_ord",
        "shipping_provider_pricing_scheme_segments",
        ["scheme_id", "active", "ord"],
        unique=False,
    )

    # Postgres：表达式唯一索引 + jsonb 回填
    if not sqlite:
        # 防重复段：同一 scheme 下 (min, max) 唯一，∞ 用大数表达
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_spss_scheme_min_max
            ON shipping_provider_pricing_scheme_segments (
              scheme_id,
              min_kg,
              COALESCE(max_kg, 999999.000)
            );
            """
        )

        # 回填：从 segments_json 读取（形状：[{min:"0",max:"1"}, {min:"1",max:"2"}, {min:"2",max:""}]）
        # - ord 从 0 开始
        # - max 为空字符串 -> NULL（∞）
        op.execute(
            """
            INSERT INTO shipping_provider_pricing_scheme_segments (scheme_id, ord, min_kg, max_kg, active)
            SELECT
              s.id AS scheme_id,
              (x.ord - 1) AS ord,
              NULLIF(BTRIM(x.elem->>'min'), '')::numeric(10,3) AS min_kg,
              NULLIF(BTRIM(x.elem->>'max'), '')::numeric(10,3) AS max_kg,
              true AS active
            FROM shipping_provider_pricing_schemes s
            CROSS JOIN LATERAL jsonb_array_elements(s.segments_json::jsonb) WITH ORDINALITY AS x(elem, ord)
            WHERE s.segments_json IS NOT NULL
              AND jsonb_typeof(s.segments_json::jsonb) = 'array';
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    sqlite = _is_sqlite(bind)

    insp = sa.inspect(bind)
    schema = None if sqlite else "public"

    if "shipping_provider_pricing_scheme_segments" not in insp.get_table_names(schema=schema):
        return

    if not sqlite:
        op.execute("DROP INDEX IF EXISTS uq_spss_scheme_min_max;")

    op.drop_index("ix_spss_scheme_active_ord", table_name="shipping_provider_pricing_scheme_segments")
    op.drop_table("shipping_provider_pricing_scheme_segments")
