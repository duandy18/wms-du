"""pms master data governance

Revision ID: d8f6a2b41c9e
Revises: b6d3e914a8c2
Create Date: 2026-04-29 19:55:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d8f6a2b41c9e"
down_revision: Union[str, Sequence[str], None] = "b6d3e914a8c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rename_sequence_if_exists(old_name: str, new_name: str, table_name: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'S'
               AND n.nspname = 'public'
               AND c.relname = '{old_name}'
          ) THEN
            ALTER SEQUENCE public.{old_name} RENAME TO {new_name};
          END IF;

          IF EXISTS (
            SELECT 1
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'S'
               AND n.nspname = 'public'
               AND c.relname = '{new_name}'
          ) THEN
            ALTER SEQUENCE public.{new_name} OWNED BY public.{table_name}.id;
            ALTER TABLE public.{table_name}
              ALTER COLUMN id SET DEFAULT nextval('public.{new_name}'::regclass);
          END IF;
        END $$;
        """
    )


def _rename_constraint_if_exists(table_name: str, old_name: str, new_name: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
              JOIN pg_namespace n ON n.oid = t.relnamespace
             WHERE n.nspname = 'public'
               AND t.relname = '{table_name}'
               AND c.conname = '{old_name}'
          ) THEN
            ALTER TABLE public.{table_name} RENAME CONSTRAINT {old_name} TO {new_name};
          END IF;
        END $$;
        """
    )


def _rename_index_if_exists(old_name: str, new_name: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'i'
               AND n.nspname = 'public'
               AND c.relname = '{old_name}'
          ) THEN
            ALTER INDEX public.{old_name} RENAME TO {new_name};
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 品牌 / 内部分类从 SKU 编码字典提升为 PMS 商品主数据真相表。
    op.rename_table("sku_code_brands", "pms_brands")
    _rename_sequence_if_exists("sku_code_brands_id_seq", "pms_brands_id_seq", "pms_brands")
    _rename_constraint_if_exists("pms_brands", "sku_code_brands_pkey", "pms_brands_pkey")
    _rename_constraint_if_exists("pms_brands", "uq_sku_code_brands_name_cn", "uq_pms_brands_name_cn")
    _rename_constraint_if_exists("pms_brands", "uq_sku_code_brands_code", "uq_pms_brands_code")

    op.rename_table("sku_business_categories", "pms_business_categories")
    _rename_sequence_if_exists(
        "sku_business_categories_id_seq",
        "pms_business_categories_id_seq",
        "pms_business_categories",
    )
    _rename_constraint_if_exists(
        "pms_business_categories",
        "sku_business_categories_pkey",
        "pms_business_categories_pkey",
    )
    _rename_constraint_if_exists(
        "pms_business_categories",
        "sku_business_categories_parent_id_fkey",
        "fk_pms_business_categories_parent",
    )
    _rename_constraint_if_exists(
        "pms_business_categories",
        "ck_sku_business_categories_level",
        "ck_pms_business_categories_level",
    )
    _rename_constraint_if_exists(
        "pms_business_categories",
        "ck_sku_business_categories_product_kind",
        "ck_pms_business_categories_product_kind_old",
    )
    _rename_constraint_if_exists(
        "pms_business_categories",
        "uq_sku_business_categories_parent_code",
        "uq_pms_business_categories_parent_code",
    )
    _rename_constraint_if_exists(
        "pms_business_categories",
        "uq_sku_business_categories_path_code",
        "uq_pms_business_categories_path_code",
    )
    _rename_index_if_exists(
        "ix_sku_business_categories_parent_id",
        "ix_pms_business_categories_parent_id",
    )
    _rename_index_if_exists(
        "ix_sku_business_categories_product_kind",
        "ix_pms_business_categories_product_kind",
    )

    op.execute(
        """
        ALTER TABLE pms_business_categories
        DROP CONSTRAINT IF EXISTS ck_pms_business_categories_product_kind_old
        """
    )
    op.create_check_constraint(
        "ck_pms_business_categories_product_kind",
        "pms_business_categories",
        "product_kind in ('FOOD', 'SUPPLY', 'OTHER')",
    )

    # 2) items 只保留规范化引用，不再承载 brand/category 自由文本真相。
    op.add_column("items", sa.Column("brand_id", sa.Integer(), nullable=True))
    op.add_column("items", sa.Column("category_id", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_items_brand",
        "items",
        "pms_brands",
        ["brand_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_items_category",
        "items",
        "pms_business_categories",
        ["category_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_items_brand_id", "items", ["brand_id"])
    op.create_index("ix_items_category_id", "items", ["category_id"])

    # 3) 从旧 items.brand/category 文本做一次性结构化迁移。
    op.execute(
        """
        INSERT INTO pms_brands (
          name_cn,
          code,
          is_active,
          is_locked,
          sort_order,
          remark,
          created_at,
          updated_at
        )
        SELECT
          x.brand_name,
          x.brand_code,
          TRUE,
          FALSE,
          0,
          'migrated from items.brand',
          CURRENT_TIMESTAMP,
          CURRENT_TIMESTAMP
        FROM (
          SELECT DISTINCT
            trim(brand) AS brand_name,
            upper('BR' || substr(md5(trim(brand)), 1, 10)) AS brand_code
          FROM items
          WHERE brand IS NOT NULL
            AND trim(brand) <> ''
        ) x
        ON CONFLICT (name_cn) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO pms_business_categories (
          parent_id,
          level,
          product_kind,
          category_name,
          category_code,
          path_code,
          is_leaf,
          is_active,
          is_locked,
          sort_order,
          remark,
          created_at,
          updated_at
        )
        SELECT
          NULL,
          1,
          'OTHER',
          x.category_name,
          x.category_code,
          x.category_code,
          TRUE,
          TRUE,
          FALSE,
          0,
          'migrated from items.category',
          CURRENT_TIMESTAMP,
          CURRENT_TIMESTAMP
        FROM (
          SELECT DISTINCT
            trim(category) AS category_name,
            upper('CAT' || substr(md5(trim(category)), 1, 10)) AS category_code
          FROM items
          WHERE category IS NOT NULL
            AND trim(category) <> ''
        ) x
        ON CONFLICT (path_code) DO NOTHING
        """
    )

    op.execute(
        """
        UPDATE items i
           SET brand_id = b.id
          FROM pms_brands b
         WHERE i.brand IS NOT NULL
           AND trim(i.brand) <> ''
           AND b.name_cn = trim(i.brand)
        """
    )

    op.execute(
        """
        UPDATE items i
           SET category_id = c.id
          FROM pms_business_categories c
         WHERE i.category IS NOT NULL
           AND trim(i.category) <> ''
           AND c.category_name = trim(i.category)
           AND c.product_kind = 'OTHER'
        """
    )

    op.drop_index("ix_items_brand", table_name="items")
    op.drop_index("ix_items_category", table_name="items")
    op.drop_column("items", "brand")
    op.drop_column("items", "category")

    # 4) 属性模板 / 选项 / 商品属性值。
    op.create_table(
        "item_attribute_defs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name_cn", sa.String(length=128), nullable=False),
        sa.Column("name_en", sa.String(length=128), nullable=True),
        sa.Column("product_kind", sa.String(length=16), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("value_type", sa.String(length=16), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=True),
        sa.Column("is_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_searchable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_filterable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_sku_segment", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "product_kind in ('FOOD', 'SUPPLY', 'OTHER', 'COMMON')",
            name="ck_item_attribute_defs_product_kind",
        ),
        sa.CheckConstraint(
            "value_type in ('TEXT', 'NUMBER', 'OPTION', 'BOOL')",
            name="ck_item_attribute_defs_value_type",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["pms_business_categories.id"],
            name="fk_item_attribute_defs_category",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", "code", name="uq_item_attribute_defs_category_code"),
    )
    op.create_index("ix_item_attribute_defs_category_id", "item_attribute_defs", ["category_id"])
    op.create_index("ix_item_attribute_defs_product_kind", "item_attribute_defs", ["product_kind"])

    op.create_table(
        "item_attribute_options",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attribute_def_id", sa.Integer(), nullable=False),
        sa.Column("option_code", sa.String(length=64), nullable=False),
        sa.Column("option_name", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["attribute_def_id"],
            ["item_attribute_defs.id"],
            name="fk_item_attribute_options_def",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attribute_def_id",
            "option_code",
            name="uq_item_attribute_options_def_code",
        ),
    )
    op.create_index("ix_item_attribute_options_def_id", "item_attribute_options", ["attribute_def_id"])

    op.create_table(
        "item_attribute_values",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("attribute_def_id", sa.Integer(), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_number", sa.Numeric(18, 6), nullable=True),
        sa.Column("value_bool", sa.Boolean(), nullable=True),
        sa.Column("value_option_id", sa.Integer(), nullable=True),
        sa.Column("value_option_code_snapshot", sa.String(length=64), nullable=True),
        sa.Column("value_unit_snapshot", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], name="fk_item_attribute_values_item", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["attribute_def_id"],
            ["item_attribute_defs.id"],
            name="fk_item_attribute_values_def",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["value_option_id"],
            ["item_attribute_options.id"],
            name="fk_item_attribute_values_option",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "attribute_def_id", name="uq_item_attribute_values_item_def"),
    )
    op.create_index("ix_item_attribute_values_item_id", "item_attribute_values", ["item_id"])
    op.create_index("ix_item_attribute_values_def_id", "item_attribute_values", ["attribute_def_id"])

    # 5) 页面注册：商品主数据下沉为真正 PMS 商品主数据模块。
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
          sort_order,
          is_active,
          inherit_permissions,
          read_permission_id,
          write_permission_id
        )
        VALUES
          ('pms.items', '商品列表', 'pms', 2, 'pms', false, true, 10, true, true, NULL, NULL),
          ('pms.brands', '品牌管理', 'pms', 2, 'pms', false, true, 12, true, true, NULL, NULL),
          ('pms.categories', '内部分类', 'pms', 2, 'pms', false, true, 14, true, true, NULL, NULL),
          ('pms.item_attributes', '属性模板', 'pms', 2, 'pms', false, true, 16, true, true, NULL, NULL)
        ON CONFLICT (code) DO UPDATE SET
          name = EXCLUDED.name,
          parent_code = EXCLUDED.parent_code,
          level = EXCLUDED.level,
          domain_code = EXCLUDED.domain_code,
          show_in_topbar = EXCLUDED.show_in_topbar,
          show_in_sidebar = EXCLUDED.show_in_sidebar,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active,
          inherit_permissions = EXCLUDED.inherit_permissions,
          read_permission_id = EXCLUDED.read_permission_id,
          write_permission_id = EXCLUDED.write_permission_id
        """
    )

    op.execute(
        """
        INSERT INTO page_route_prefixes (route_prefix, page_code, sort_order, is_active)
        VALUES
          ('/items', 'pms.items', 10, true),
          ('/pms/brands', 'pms.brands', 10, true),
          ('/pms/categories', 'pms.categories', 10, true),
          ('/pms/item-attribute-defs', 'pms.item_attributes', 10, true)
        ON CONFLICT (route_prefix) DO UPDATE SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    op.execute("DELETE FROM page_registry WHERE code = 'wms.masterdata.items'")


def downgrade() -> None:
    """Downgrade schema."""

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
          sort_order,
          is_active,
          inherit_permissions,
          read_permission_id,
          write_permission_id
        )
        VALUES
          ('wms.masterdata.items', '商品管理', 'pms', 2, 'pms', false, true, 10, true, true, NULL, NULL)
        ON CONFLICT (code) DO UPDATE SET
          name = EXCLUDED.name,
          parent_code = EXCLUDED.parent_code,
          level = EXCLUDED.level,
          domain_code = EXCLUDED.domain_code,
          show_in_topbar = EXCLUDED.show_in_topbar,
          show_in_sidebar = EXCLUDED.show_in_sidebar,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active,
          inherit_permissions = EXCLUDED.inherit_permissions,
          read_permission_id = EXCLUDED.read_permission_id,
          write_permission_id = EXCLUDED.write_permission_id
        """
    )
    op.execute(
        """
        INSERT INTO page_route_prefixes (route_prefix, page_code, sort_order, is_active)
        VALUES ('/items', 'wms.masterdata.items', 10, true)
        ON CONFLICT (route_prefix) DO UPDATE SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )
    op.execute(
        """
        DELETE FROM page_route_prefixes
         WHERE route_prefix IN ('/pms/brands', '/pms/categories', '/pms/item-attribute-defs')
        """
    )
    op.execute(
        """
        DELETE FROM page_registry
         WHERE code IN ('pms.items', 'pms.brands', 'pms.categories', 'pms.item_attributes')
        """
    )

    op.add_column("items", sa.Column("brand", sa.String(length=64), nullable=True))
    op.add_column("items", sa.Column("category", sa.String(length=64), nullable=True))

    op.execute(
        """
        UPDATE items i
           SET brand = b.name_cn
          FROM pms_brands b
         WHERE i.brand_id = b.id
        """
    )
    op.execute(
        """
        UPDATE items i
           SET category = c.category_name
          FROM pms_business_categories c
         WHERE i.category_id = c.id
        """
    )

    op.create_index("ix_items_brand", "items", ["brand"])
    op.create_index("ix_items_category", "items", ["category"])

    op.drop_index("ix_item_attribute_values_def_id", table_name="item_attribute_values")
    op.drop_index("ix_item_attribute_values_item_id", table_name="item_attribute_values")
    op.drop_table("item_attribute_values")

    op.drop_index("ix_item_attribute_options_def_id", table_name="item_attribute_options")
    op.drop_table("item_attribute_options")

    op.drop_index("ix_item_attribute_defs_product_kind", table_name="item_attribute_defs")
    op.drop_index("ix_item_attribute_defs_category_id", table_name="item_attribute_defs")
    op.drop_table("item_attribute_defs")

    op.drop_index("ix_items_category_id", table_name="items")
    op.drop_index("ix_items_brand_id", table_name="items")
    op.drop_constraint("fk_items_category", "items", type_="foreignkey")
    op.drop_constraint("fk_items_brand", "items", type_="foreignkey")
    op.drop_column("items", "category_id")
    op.drop_column("items", "brand_id")

    op.execute("ALTER TABLE pms_business_categories DROP CONSTRAINT IF EXISTS ck_pms_business_categories_product_kind")
    op.create_check_constraint(
        "ck_sku_business_categories_product_kind",
        "pms_business_categories",
        "product_kind in ('FOOD', 'SUPPLY')",
    )

    _rename_index_if_exists("ix_pms_business_categories_product_kind", "ix_sku_business_categories_product_kind")
    _rename_index_if_exists("ix_pms_business_categories_parent_id", "ix_sku_business_categories_parent_id")

    _rename_constraint_if_exists(
        "pms_business_categories",
        "uq_pms_business_categories_path_code",
        "uq_sku_business_categories_path_code",
    )
    _rename_constraint_if_exists(
        "pms_business_categories",
        "uq_pms_business_categories_parent_code",
        "uq_sku_business_categories_parent_code",
    )
    _rename_constraint_if_exists(
        "pms_business_categories",
        "ck_pms_business_categories_level",
        "ck_sku_business_categories_level",
    )
    _rename_constraint_if_exists(
        "pms_business_categories",
        "fk_pms_business_categories_parent",
        "sku_business_categories_parent_id_fkey",
    )
    _rename_constraint_if_exists(
        "pms_business_categories",
        "pms_business_categories_pkey",
        "sku_business_categories_pkey",
    )
    op.rename_table("pms_business_categories", "sku_business_categories")
    _rename_sequence_if_exists(
        "pms_business_categories_id_seq",
        "sku_business_categories_id_seq",
        "sku_business_categories",
    )

    _rename_constraint_if_exists("pms_brands", "uq_pms_brands_code", "uq_sku_code_brands_code")
    _rename_constraint_if_exists("pms_brands", "uq_pms_brands_name_cn", "uq_sku_code_brands_name_cn")
    _rename_constraint_if_exists("pms_brands", "pms_brands_pkey", "sku_code_brands_pkey")
    op.rename_table("pms_brands", "sku_code_brands")
    _rename_sequence_if_exists("pms_brands_id_seq", "sku_code_brands_id_seq", "sku_code_brands")
