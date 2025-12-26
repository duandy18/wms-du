"""add_segment_templates_tables

Revision ID: 473f09545f17
Revises: 7ec000d0d03e
Create Date: 2025-12-26 13:15:53.967418

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "473f09545f17"
down_revision: Union[str, Sequence[str], None] = "7ec000d0d03e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_sqlite(bind) -> bool:
    return (bind.dialect.name or "").lower() == "sqlite"


def upgrade() -> None:
    bind = op.get_bind()
    sqlite = _is_sqlite(bind)

    insp = sa.inspect(bind)
    schema = None if sqlite else "public"

    # 依赖表不存在就不做
    if "shipping_provider_pricing_schemes" not in insp.get_table_names(schema=schema):
        return

    # -------------------------
    # 1) templates 主表
    # -------------------------
    if "shipping_provider_pricing_scheme_segment_templates" not in insp.get_table_names(schema=schema):
        op.create_table(
            "shipping_provider_pricing_scheme_segment_templates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("scheme_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'draft'"),
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
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
        )
        op.create_index(
            "ix_spsst_scheme_active",
            "shipping_provider_pricing_scheme_segment_templates",
            ["scheme_id", "is_active"],
            unique=False,
        )

    # -------------------------
    # 2) template_items 段表
    # -------------------------
    if "shipping_provider_pricing_scheme_segment_template_items" not in insp.get_table_names(schema=schema):
        op.create_table(
            "shipping_provider_pricing_scheme_segment_template_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("template_id", sa.Integer(), nullable=False),
            sa.Column("ord", sa.Integer(), nullable=False),
            sa.Column("min_kg", sa.Numeric(10, 3), nullable=False),
            sa.Column("max_kg", sa.Numeric(10, 3), nullable=True),  # NULL = ∞
            sa.Column(
                "active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
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
                ["template_id"],
                ["shipping_provider_pricing_scheme_segment_templates.id"],
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint("template_id", "ord", name="uq_spssti_tpl_ord"),
            sa.CheckConstraint("min_kg >= 0", name="ck_spssti_min_nonneg"),
            sa.CheckConstraint("(max_kg IS NULL) OR (max_kg > min_kg)", name="ck_spssti_max_gt_min"),
        )
        op.create_index(
            "ix_spssti_tpl_ord",
            "shipping_provider_pricing_scheme_segment_template_items",
            ["template_id", "ord"],
            unique=False,
        )

        # Postgres：表达式唯一索引（∞ 用大数表达）
        if not sqlite:
            op.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_spssti_tpl_min_max
                ON shipping_provider_pricing_scheme_segment_template_items (
                  template_id,
                  min_kg,
                  COALESCE(max_kg, 999999.000)
                );
                """
            )

    # -------------------------
    # 3) 回填基线模板（每个 scheme 至多一个）
    # - 从现有 scheme_segments 表生成一个 published+active 模板
    # -------------------------
    if not sqlite:
        # 创建模板：对每个 scheme_id（segments 表里出现过的）创建一个模板
        op.execute(
            """
            INSERT INTO shipping_provider_pricing_scheme_segment_templates
              (scheme_id, name, status, is_active, published_at, created_at, updated_at)
            SELECT
              s.scheme_id,
              'Legacy migrated' AS name,
              'published' AS status,
              true AS is_active,
              CURRENT_TIMESTAMP AS published_at,
              CURRENT_TIMESTAMP AS created_at,
              CURRENT_TIMESTAMP AS updated_at
            FROM (
              SELECT scheme_id
              FROM shipping_provider_pricing_scheme_segments
              GROUP BY scheme_id
            ) s
            WHERE NOT EXISTS (
              SELECT 1
              FROM shipping_provider_pricing_scheme_segment_templates t
              WHERE t.scheme_id = s.scheme_id
            );
            """
        )

        # 关闭同 scheme 的其它 active（保险，避免历史脏数据导致多个 active）
        op.execute(
            """
            UPDATE shipping_provider_pricing_scheme_segment_templates t
            SET is_active = false
            WHERE t.name <> 'Legacy migrated'
              AND EXISTS (
                SELECT 1 FROM shipping_provider_pricing_scheme_segment_templates x
                WHERE x.scheme_id = t.scheme_id AND x.name = 'Legacy migrated' AND x.is_active = true
              );
            """
        )

        # 回填 items：复制 scheme_segments -> template_items（active 跟随）
        op.execute(
            """
            INSERT INTO shipping_provider_pricing_scheme_segment_template_items
              (template_id, ord, min_kg, max_kg, active, created_at, updated_at)
            SELECT
              t.id AS template_id,
              seg.ord,
              seg.min_kg,
              seg.max_kg,
              seg.active,
              CURRENT_TIMESTAMP,
              CURRENT_TIMESTAMP
            FROM shipping_provider_pricing_scheme_segment_templates t
            JOIN shipping_provider_pricing_scheme_segments seg
              ON seg.scheme_id = t.scheme_id
            WHERE t.name = 'Legacy migrated'
              AND t.is_active = true;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    sqlite = _is_sqlite(bind)

    insp = sa.inspect(bind)
    schema = None if sqlite else "public"

    if "shipping_provider_pricing_scheme_segment_template_items" in insp.get_table_names(schema=schema):
        if not sqlite:
            op.execute("DROP INDEX IF EXISTS uq_spssti_tpl_min_max;")
        op.drop_index(
            "ix_spssti_tpl_ord",
            table_name="shipping_provider_pricing_scheme_segment_template_items",
        )
        op.drop_table("shipping_provider_pricing_scheme_segment_template_items")

    if "shipping_provider_pricing_scheme_segment_templates" in insp.get_table_names(schema=schema):
        op.drop_index(
            "ix_spsst_scheme_active",
            table_name="shipping_provider_pricing_scheme_segment_templates",
        )
        op.drop_table("shipping_provider_pricing_scheme_segment_templates")
