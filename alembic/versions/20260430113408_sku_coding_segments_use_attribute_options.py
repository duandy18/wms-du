"""Cut SKU coding segments over to PMS attribute options.

Revision ID: 20260430113408
Revises: 20260430111143
Create Date: 2026-04-30

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260430113408"
down_revision: Union[str, Sequence[str], None] = "20260430111143"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 先把旧 SKU 字典完整升迁到 PMS 属性模板 / 预设选项。
    op.execute(
        """
        INSERT INTO item_attribute_defs (
            code,
            name_cn,
            name_en,
            product_kind,
            value_type,
            selection_mode,
            unit,
            is_item_required,
            is_sku_required,
            is_sku_segment,
            is_active,
            is_locked,
            sort_order,
            remark
        )
        SELECT
            g.group_code,
            CASE g.group_code
                WHEN 'LIFE_STAGE' THEN '适用阶段'
                WHEN 'PROCESS' THEN '工艺类型'
                WHEN 'FLAVOR' THEN '口味'
                WHEN 'FUNCTION' THEN '功能属性'
                WHEN 'MODEL' THEN '型号/系列'
                WHEN 'MATERIAL' THEN '材质'
                WHEN 'COLOR' THEN '颜色'
                WHEN 'STRUCTURE' THEN '结构'
                WHEN 'FEATURE' THEN '功能特性'
                ELSE g.group_name
            END AS name_cn,
            NULL AS name_en,
            g.product_kind,
            'OPTION' AS value_type,
            CASE WHEN g.is_multi_select THEN 'MULTI' ELSE 'SINGLE' END AS selection_mode,
            NULL AS unit,
            FALSE AS is_item_required,
            g.is_required AS is_sku_required,
            TRUE AS is_sku_segment,
            g.is_active AS is_active,
            FALSE AS is_locked,
            g.sort_order AS sort_order,
            '由 SKU 编码字典升迁为属性模板预设选项真相源' AS remark
        FROM sku_code_term_groups g
        WHERE g.product_kind IN ('FOOD', 'SUPPLY')
        ON CONFLICT (product_kind, code) DO UPDATE
           SET value_type = 'OPTION',
               selection_mode = EXCLUDED.selection_mode,
               is_sku_required = EXCLUDED.is_sku_required,
               is_sku_segment = TRUE,
               updated_at = now()
        """
    )

    op.execute(
        """
        INSERT INTO item_attribute_options (
            attribute_def_id,
            option_code,
            option_name,
            is_active,
            is_locked,
            sort_order
        )
        SELECT
            d.id,
            t.code,
            t.name_cn,
            t.is_active,
            t.is_locked,
            t.sort_order
        FROM sku_code_terms t
        JOIN sku_code_term_groups g ON g.id = t.group_id
        JOIN item_attribute_defs d
          ON d.product_kind = g.product_kind
         AND d.code = g.group_code
        WHERE g.product_kind IN ('FOOD', 'SUPPLY')
        ON CONFLICT (attribute_def_id, option_code) DO NOTHING
        """
    )

    # 2) SKU 模板段从旧 term_group_id 改为 attribute_def_id。
    op.add_column("sku_code_template_segments", sa.Column("attribute_def_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_sku_code_template_segments_attribute_def",
        "sku_code_template_segments",
        "item_attribute_defs",
        ["attribute_def_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_sku_code_template_segments_attribute_def_id",
        "sku_code_template_segments",
        ["attribute_def_id"],
    )

    # 先删除旧 check，否则 ATTRIBUTE_OPTION 写不进去。
    op.drop_constraint("ck_sku_code_template_segments_source_type", "sku_code_template_segments", type_="check")

    op.execute(
        """
        UPDATE sku_code_template_segments s
           SET attribute_def_id = d.id,
               source_type = 'ATTRIBUTE_OPTION'
          FROM sku_code_templates t,
               sku_code_term_groups g,
               item_attribute_defs d
         WHERE s.template_id = t.id
           AND s.term_group_id = g.id
           AND s.source_type = 'TERM'
           AND d.product_kind = t.product_kind
           AND d.code = g.group_code
           AND d.value_type = 'OPTION'
           AND d.is_sku_segment IS TRUE
        """
    )

    op.execute(
        """
        DO $sku_cutover$
        BEGIN
            IF EXISTS (
                SELECT 1
                  FROM sku_code_template_segments
                 WHERE source_type = 'TERM'
                   AND attribute_def_id IS NULL
            ) THEN
                RAISE EXCEPTION 'Migration blocked: some SKU TERM segments could not be mapped to item_attribute_defs';
            END IF;
        END
        $sku_cutover$;
        """
    )

    op.create_check_constraint(
        "ck_sku_code_template_segments_source_type",
        "sku_code_template_segments",
        "source_type in ('BRAND', 'CATEGORY', 'ATTRIBUTE_OPTION', 'TEXT', 'SPEC')",
    )
    op.create_check_constraint(
        "ck_sku_code_template_segments_attribute_def",
        "sku_code_template_segments",
        "((source_type = 'ATTRIBUTE_OPTION' and attribute_def_id is not null) or (source_type <> 'ATTRIBUTE_OPTION' and attribute_def_id is null))",
    )

    op.drop_constraint("sku_code_template_segments_term_group_id_fkey", "sku_code_template_segments", type_="foreignkey")
    op.drop_column("sku_code_template_segments", "term_group_id")

    # 3) SKU 编码页面注册收口：只有一个页面时，直接提升为 PMS 二级页。
    op.execute(
        """
        DELETE FROM page_route_prefixes
        WHERE route_prefix IN (
          '/items/sku-coding/generator',
          '/items/sku-coding/dictionaries'
        )
        """
    )
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN (
          'pms.sku_coding.generator',
          'pms.sku_coding.dictionaries'
        )
        """
    )
    op.execute(
        """
        INSERT INTO page_registry (
          code,
          name,
          parent_code,
          level,
          domain_code,
          show_in_topbar,
          show_in_sidebar,
          inherit_permissions,
          read_permission_id,
          write_permission_id,
          sort_order,
          is_active
        )
        VALUES (
          'pms.sku_coding',
          'SKU 编码',
          'pms',
          2,
          'pms',
          FALSE,
          TRUE,
          TRUE,
          NULL,
          NULL,
          50,
          TRUE
        )
        ON CONFLICT (code) DO UPDATE
        SET
          name = EXCLUDED.name,
          parent_code = EXCLUDED.parent_code,
          level = EXCLUDED.level,
          domain_code = EXCLUDED.domain_code,
          show_in_topbar = EXCLUDED.show_in_topbar,
          show_in_sidebar = EXCLUDED.show_in_sidebar,
          inherit_permissions = EXCLUDED.inherit_permissions,
          read_permission_id = EXCLUDED.read_permission_id,
          write_permission_id = EXCLUDED.write_permission_id,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          route_prefix,
          page_code,
          sort_order,
          is_active
        )
        VALUES (
          '/items/sku-coding',
          'pms.sku_coding',
          10,
          TRUE
        )
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 4) 一步到位：旧 SKU 字典表退役，不再保留双字典。
    op.drop_table("sku_code_term_aliases")
    op.drop_table("sku_code_terms")
    op.drop_table("sku_code_term_groups")


def downgrade() -> None:
    # 可逆恢复旧三级页结构。
    op.execute(
        """
        DELETE FROM page_route_prefixes
        WHERE route_prefix = '/items/sku-coding'
        """
    )
    op.execute(
        """
        INSERT INTO page_registry (
          code,
          name,
          parent_code,
          level,
          domain_code,
          show_in_topbar,
          show_in_sidebar,
          inherit_permissions,
          read_permission_id,
          write_permission_id,
          sort_order,
          is_active
        )
        VALUES (
          'pms.sku_coding',
          'SKU编码',
          'pms',
          2,
          'pms',
          FALSE,
          TRUE,
          TRUE,
          NULL,
          NULL,
          50,
          TRUE
        )
        ON CONFLICT (code) DO UPDATE
        SET
          name = EXCLUDED.name,
          parent_code = EXCLUDED.parent_code,
          level = EXCLUDED.level,
          domain_code = EXCLUDED.domain_code,
          show_in_topbar = EXCLUDED.show_in_topbar,
          show_in_sidebar = EXCLUDED.show_in_sidebar,
          inherit_permissions = EXCLUDED.inherit_permissions,
          read_permission_id = EXCLUDED.read_permission_id,
          write_permission_id = EXCLUDED.write_permission_id,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )
    op.execute(
        """
        INSERT INTO page_registry (
          code,
          name,
          parent_code,
          level,
          domain_code,
          show_in_topbar,
          show_in_sidebar,
          inherit_permissions,
          read_permission_id,
          write_permission_id,
          sort_order,
          is_active
        )
        VALUES
          (
            'pms.sku_coding.generator',
            '编码生成',
            'pms.sku_coding',
            3,
            'pms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            10,
            TRUE
          ),
          (
            'pms.sku_coding.dictionaries',
            '字典维护',
            'pms.sku_coding',
            3,
            'pms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            20,
            TRUE
          )
        ON CONFLICT (code) DO UPDATE
        SET
          name = EXCLUDED.name,
          parent_code = EXCLUDED.parent_code,
          level = EXCLUDED.level,
          domain_code = EXCLUDED.domain_code,
          show_in_topbar = EXCLUDED.show_in_topbar,
          show_in_sidebar = EXCLUDED.show_in_sidebar,
          inherit_permissions = EXCLUDED.inherit_permissions,
          read_permission_id = EXCLUDED.read_permission_id,
          write_permission_id = EXCLUDED.write_permission_id,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          route_prefix,
          page_code,
          sort_order,
          is_active
        )
        VALUES
          (
            '/items/sku-coding/generator',
            'pms.sku_coding.generator',
            10,
            TRUE
          ),
          (
            '/items/sku-coding/dictionaries',
            'pms.sku_coding.dictionaries',
            20,
            TRUE
          )
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

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
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
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
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
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
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["sku_code_terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_alias", name="uq_sku_code_term_aliases_normalized"),
    )
    op.create_index("ix_sku_code_term_aliases_term_id", "sku_code_term_aliases", ["term_id"])

    op.execute(
        """
        INSERT INTO sku_code_term_groups (
            product_kind,
            group_code,
            group_name,
            is_multi_select,
            is_required,
            sort_order,
            is_active,
            remark
        )
        SELECT
            d.product_kind,
            d.code,
            d.name_cn,
            d.selection_mode = 'MULTI',
            d.is_sku_required,
            d.sort_order,
            d.is_active,
            d.remark
        FROM item_attribute_defs d
        WHERE d.product_kind IN ('FOOD', 'SUPPLY')
          AND d.value_type = 'OPTION'
          AND d.is_sku_segment IS TRUE
        ON CONFLICT (product_kind, group_code) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO sku_code_terms (
            group_id,
            name_cn,
            code,
            sort_order,
            is_active,
            is_locked
        )
        SELECT
            g.id,
            o.option_name,
            o.option_code,
            o.sort_order,
            o.is_active,
            o.is_locked
        FROM item_attribute_options o
        JOIN item_attribute_defs d ON d.id = o.attribute_def_id
        JOIN sku_code_term_groups g
          ON g.product_kind = d.product_kind
         AND g.group_code = d.code
        WHERE d.product_kind IN ('FOOD', 'SUPPLY')
          AND d.value_type = 'OPTION'
          AND d.is_sku_segment IS TRUE
        ON CONFLICT (group_id, code) DO NOTHING
        """
    )

    op.add_column("sku_code_template_segments", sa.Column("term_group_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "sku_code_template_segments_term_group_id_fkey",
        "sku_code_template_segments",
        "sku_code_term_groups",
        ["term_group_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("ck_sku_code_template_segments_attribute_def", "sku_code_template_segments", type_="check")
    op.drop_constraint("ck_sku_code_template_segments_source_type", "sku_code_template_segments", type_="check")

    op.execute(
        """
        UPDATE sku_code_template_segments s
           SET term_group_id = g.id,
               source_type = 'TERM'
          FROM sku_code_templates t,
               item_attribute_defs d,
               sku_code_term_groups g
         WHERE s.template_id = t.id
           AND s.attribute_def_id = d.id
           AND s.source_type = 'ATTRIBUTE_OPTION'
           AND g.product_kind = t.product_kind
           AND g.group_code = d.code
        """
    )

    op.create_check_constraint(
        "ck_sku_code_template_segments_source_type",
        "sku_code_template_segments",
        "source_type in ('BRAND', 'CATEGORY', 'TERM', 'TEXT', 'SPEC')",
    )

    op.drop_index("ix_sku_code_template_segments_attribute_def_id", table_name="sku_code_template_segments")
    op.drop_constraint("fk_sku_code_template_segments_attribute_def", "sku_code_template_segments", type_="foreignkey")
    op.drop_column("sku_code_template_segments", "attribute_def_id")
