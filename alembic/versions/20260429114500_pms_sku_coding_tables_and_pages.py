"""pms sku coding tables and pages

Revision ID: 20260429114500
Revises: 3eb4afa444e5
Create Date: 2026-04-29 11:45:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260429114500"
down_revision = "3eb4afa444e5"
branch_labels = None
depends_on = None


def _seed_term_groups() -> None:
    op.execute(
        """
        INSERT INTO sku_code_term_groups(product_kind, group_code, group_name, is_multi_select, is_required, sort_order, is_active, remark)
        VALUES
          ('FOOD', 'LIFE_STAGE', '适用阶段', false, false, 10, true, NULL),
          ('FOOD', 'PROCESS', '工艺/系列', true, false, 20, true, NULL),
          ('FOOD', 'FLAVOR', '口味/蛋白', true, true, 30, true, NULL),
          ('FOOD', 'FUNCTION', '功能属性', true, false, 40, true, NULL),
          ('SUPPLY', 'MODEL', '型号/系列', false, false, 10, true, NULL),
          ('SUPPLY', 'MATERIAL', '材质', true, false, 20, true, NULL),
          ('SUPPLY', 'COLOR', '颜色', false, false, 30, true, NULL),
          ('SUPPLY', 'STRUCTURE', '结构', true, false, 40, true, NULL),
          ('SUPPLY', 'FEATURE', '功能特征', true, false, 50, true, NULL)
        ON CONFLICT (product_kind, group_code) DO NOTHING
        """
    )


def _seed_templates() -> None:
    op.execute(
        """
        INSERT INTO sku_code_templates(template_code, product_kind, template_name, prefix, separator, is_active, remark)
        VALUES
          ('FOOD_DEFAULT', 'FOOD', '食品默认 SKU 编码模板', 'SKU', '-', true, 'SKU-[品牌]-[分类]-[适用阶段]-[工艺/系列]-[口味/蛋白]-[功能属性]-[规格]'),
          ('SUPPLY_DEFAULT', 'SUPPLY', '用品默认 SKU 编码模板', 'SKU', '-', true, 'SKU-[品牌]-[分类]-[型号/系列]-[材质]-[规格/容量]-[颜色]')
        ON CONFLICT (template_code) DO NOTHING
        """
    )

    op.execute(
        """
        WITH food AS (
          SELECT id FROM sku_code_templates WHERE template_code = 'FOOD_DEFAULT'
        ), supply AS (
          SELECT id FROM sku_code_templates WHERE template_code = 'SUPPLY_DEFAULT'
        ), groups AS (
          SELECT id, product_kind, group_code FROM sku_code_term_groups
        )
        INSERT INTO sku_code_template_segments(template_id, segment_key, source_type, term_group_id, is_required, is_multi_select, sort_order)
        SELECT food.id, 'BRAND', 'BRAND', NULL::integer, true, false, 10 FROM food
        UNION ALL SELECT food.id, 'CATEGORY', 'CATEGORY', NULL::integer, true, false, 20 FROM food
        UNION ALL SELECT food.id, 'LIFE_STAGE', 'TERM', g.id, false, false, 30 FROM food, groups g WHERE g.product_kind='FOOD' AND g.group_code='LIFE_STAGE'
        UNION ALL SELECT food.id, 'PROCESS', 'TERM', g.id, false, true, 40 FROM food, groups g WHERE g.product_kind='FOOD' AND g.group_code='PROCESS'
        UNION ALL SELECT food.id, 'FLAVOR', 'TERM', g.id, true, true, 50 FROM food, groups g WHERE g.product_kind='FOOD' AND g.group_code='FLAVOR'
        UNION ALL SELECT food.id, 'FUNCTION', 'TERM', g.id, false, true, 60 FROM food, groups g WHERE g.product_kind='FOOD' AND g.group_code='FUNCTION'
        UNION ALL SELECT food.id, 'SPEC', 'SPEC', NULL::integer, true, false, 70 FROM food
        UNION ALL SELECT supply.id, 'BRAND', 'BRAND', NULL::integer, true, false, 10 FROM supply
        UNION ALL SELECT supply.id, 'CATEGORY', 'CATEGORY', NULL::integer, true, false, 20 FROM supply
        UNION ALL SELECT supply.id, 'MODEL', 'TERM', g.id, false, false, 30 FROM supply, groups g WHERE g.product_kind='SUPPLY' AND g.group_code='MODEL'
        UNION ALL SELECT supply.id, 'MATERIAL', 'TERM', g.id, false, true, 40 FROM supply, groups g WHERE g.product_kind='SUPPLY' AND g.group_code='MATERIAL'
        UNION ALL SELECT supply.id, 'SPEC', 'SPEC', NULL::integer, true, false, 50 FROM supply
        UNION ALL SELECT supply.id, 'COLOR', 'TERM', g.id, false, false, 60 FROM supply, groups g WHERE g.product_kind='SUPPLY' AND g.group_code='COLOR'
        ON CONFLICT (template_id, segment_key) DO NOTHING
        """
    )


def _seed_pages() -> None:
    op.execute(
        """
        INSERT INTO page_registry (
          code, name, parent_code, level, domain_code,
          show_in_topbar, show_in_sidebar, sort_order, is_active,
          inherit_permissions, read_permission_id, write_permission_id
        )
        VALUES
          ('pms.sku_coding', 'SKU编码', 'pms', 2, 'pms', false, true, 30, true, true, NULL, NULL),
          ('pms.sku_coding.generator', '编码生成', 'pms.sku_coding', 3, 'pms', false, true, 10, true, true, NULL, NULL),
          ('pms.sku_coding.dictionaries', '字典维护', 'pms.sku_coding', 3, 'pms', false, true, 20, true, true, NULL, NULL)
        ON CONFLICT (code) DO UPDATE
        SET
          name = EXCLUDED.name,
          parent_code = EXCLUDED.parent_code,
          level = EXCLUDED.level,
          domain_code = EXCLUDED.domain_code,
          show_in_topbar = EXCLUDED.show_in_topbar,
          show_in_sidebar = EXCLUDED.show_in_sidebar,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active,
          inherit_permissions = EXCLUDED.inherit_permissions,
          read_permission_id = NULL,
          write_permission_id = NULL
        """
    )

    op.execute(
        """
        INSERT INTO page_route_prefixes(page_code, route_prefix, sort_order, is_active)
        VALUES
          ('pms.sku_coding.generator', '/items/sku-coding/generator', 10, true),
          ('pms.sku_coding.dictionaries', '/items/sku-coding/dictionaries', 20, true)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )


def upgrade() -> None:
    op.create_table(
        "sku_code_brands",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name_cn", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_locked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name_cn", name="uq_sku_code_brands_name_cn"),
        sa.UniqueConstraint("code", name="uq_sku_code_brands_code"),
    )

    op.create_table(
        "sku_business_categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("product_kind", sa.String(length=16), nullable=False),
        sa.Column("category_name", sa.String(length=128), nullable=False),
        sa.Column("category_code", sa.String(length=32), nullable=False),
        sa.Column("path_code", sa.String(length=255), nullable=False),
        sa.Column("is_leaf", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_locked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("level in (1, 2, 3)", name="ck_sku_business_categories_level"),
        sa.CheckConstraint("product_kind in ('FOOD', 'SUPPLY')", name="ck_sku_business_categories_product_kind"),
        sa.ForeignKeyConstraint(["parent_id"], ["sku_business_categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("path_code", name="uq_sku_business_categories_path_code"),
        sa.UniqueConstraint("parent_id", "category_code", name="uq_sku_business_categories_parent_code"),
    )
    op.create_index("ix_sku_business_categories_parent_id", "sku_business_categories", ["parent_id"])
    op.create_index("ix_sku_business_categories_product_kind", "sku_business_categories", ["product_kind"])

    op.create_table(
        "sku_code_term_groups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_kind", sa.String(length=16), nullable=False),
        sa.Column("group_code", sa.String(length=32), nullable=False),
        sa.Column("group_name", sa.String(length=64), nullable=False),
        sa.Column("is_multi_select", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("product_kind in ('FOOD', 'SUPPLY', 'COMMON')", name="ck_sku_code_term_groups_product_kind"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_kind", "group_code", name="uq_sku_code_term_groups_kind_code"),
    )

    op.create_table(
        "sku_code_terms",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("name_cn", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_locked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["sku_code_term_groups.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "name_cn", name="uq_sku_code_terms_group_name_cn"),
        sa.UniqueConstraint("group_id", "code", name="uq_sku_code_terms_group_code"),
    )
    op.create_index("ix_sku_code_terms_group_id", "sku_code_terms", ["group_id"])

    op.create_table(
        "sku_code_term_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("alias_name", sa.String(length=128), nullable=False),
        sa.Column("normalized_alias", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["sku_code_terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_alias", name="uq_sku_code_term_aliases_normalized"),
    )
    op.create_index("ix_sku_code_term_aliases_term_id", "sku_code_term_aliases", ["term_id"])

    op.create_table(
        "sku_code_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_code", sa.String(length=64), nullable=False),
        sa.Column("product_kind", sa.String(length=16), nullable=False),
        sa.Column("template_name", sa.String(length=128), nullable=False),
        sa.Column("prefix", sa.String(length=16), server_default=sa.text("'SKU'"), nullable=False),
        sa.Column("separator", sa.String(length=8), server_default=sa.text("'-'"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("product_kind in ('FOOD', 'SUPPLY')", name="ck_sku_code_templates_product_kind"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_code", name="uq_sku_code_templates_template_code"),
    )

    op.create_table(
        "sku_code_template_segments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("segment_key", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("term_group_id", sa.Integer(), nullable=True),
        sa.Column("is_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_multi_select", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source_type in ('BRAND', 'CATEGORY', 'TERM', 'TEXT', 'SPEC')", name="ck_sku_code_template_segments_source_type"),
        sa.ForeignKeyConstraint(["template_id"], ["sku_code_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["term_group_id"], ["sku_code_term_groups.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "segment_key", name="uq_sku_code_template_segments_template_key"),
    )
    op.create_index("ix_sku_code_template_segments_template_id", "sku_code_template_segments", ["template_id"])

    _seed_term_groups()
    _seed_templates()
    _seed_pages()


def downgrade() -> None:
    op.execute("DELETE FROM page_route_prefixes WHERE route_prefix IN ('/items/sku-coding/generator', '/items/sku-coding/dictionaries')")
    op.execute("DELETE FROM page_registry WHERE code IN ('pms.sku_coding.generator', 'pms.sku_coding.dictionaries', 'pms.sku_coding')")

    op.drop_index("ix_sku_code_template_segments_template_id", table_name="sku_code_template_segments")
    op.drop_table("sku_code_template_segments")
    op.drop_table("sku_code_templates")
    op.drop_index("ix_sku_code_term_aliases_term_id", table_name="sku_code_term_aliases")
    op.drop_table("sku_code_term_aliases")
    op.drop_index("ix_sku_code_terms_group_id", table_name="sku_code_terms")
    op.drop_table("sku_code_terms")
    op.drop_table("sku_code_term_groups")
    op.drop_index("ix_sku_business_categories_product_kind", table_name="sku_business_categories")
    op.drop_index("ix_sku_business_categories_parent_id", table_name="sku_business_categories")
    op.drop_table("sku_business_categories")
    op.drop_table("sku_code_brands")
