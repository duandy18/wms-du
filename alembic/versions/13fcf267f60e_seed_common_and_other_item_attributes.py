"""Seed COMMON and OTHER item attribute templates.

Revision ID: 13fcf267f60e
Revises: 20260430113408
Create Date: 2026-04-30

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "13fcf267f60e"
down_revision: Union[str, Sequence[str], None] = "20260430113408"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Seed COMMON / OTHER PMS item attribute templates and options."""

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
        VALUES
            ('ORIGIN', '产地', NULL, 'COMMON', 'TEXT', 'SINGLE', NULL, FALSE, FALSE, FALSE, TRUE, FALSE, 10, '通用商品属性：跨商品类型可选维护'),
            ('MANUFACTURER', '生产厂家', NULL, 'COMMON', 'TEXT', 'SINGLE', NULL, FALSE, FALSE, FALSE, TRUE, FALSE, 20, '通用商品属性：生产主体，不等同于品牌或供应商'),
            ('SERIES', '系列/产品线', NULL, 'COMMON', 'TEXT', 'SINGLE', NULL, FALSE, FALSE, FALSE, TRUE, FALSE, 30, '通用商品属性：用于记录系列或产品线'),
            ('REMARK', '商品属性备注', NULL, 'COMMON', 'TEXT', 'SINGLE', NULL, FALSE, FALSE, FALSE, TRUE, FALSE, 90, '通用商品属性：补充说明，不作为结构化字段替代'),

            ('MODEL', '型号/系列', NULL, 'OTHER', 'OPTION', 'SINGLE', NULL, FALSE, FALSE, TRUE, TRUE, FALSE, 200, 'OTHER 商品属性：型号或系列，作为可选 SKU 区分段'),
            ('MATERIAL', '材质', NULL, 'OTHER', 'OPTION', 'MULTI', NULL, FALSE, FALSE, TRUE, TRUE, FALSE, 210, 'OTHER 商品属性：材质，可多选'),
            ('COLOR', '颜色', NULL, 'OTHER', 'OPTION', 'SINGLE', NULL, FALSE, FALSE, TRUE, TRUE, FALSE, 220, 'OTHER 商品属性：颜色，作为可选 SKU 区分段'),
            ('SIZE', '尺寸/规格档', NULL, 'OTHER', 'OPTION', 'SINGLE', NULL, FALSE, FALSE, TRUE, TRUE, FALSE, 230, 'OTHER 商品属性：结构化尺寸或规格档，不替代商品规格文本'),
            ('USAGE', '用途/适用场景', NULL, 'OTHER', 'OPTION', 'MULTI', NULL, FALSE, FALSE, FALSE, TRUE, FALSE, 240, 'OTHER 商品属性：运营筛选与场景描述，不参与 SKU 段')
        ON CONFLICT (product_kind, code) DO UPDATE
           SET name_cn = EXCLUDED.name_cn,
               name_en = EXCLUDED.name_en,
               value_type = EXCLUDED.value_type,
               selection_mode = EXCLUDED.selection_mode,
               unit = EXCLUDED.unit,
               is_item_required = EXCLUDED.is_item_required,
               is_sku_required = EXCLUDED.is_sku_required,
               is_sku_segment = EXCLUDED.is_sku_segment,
               is_active = EXCLUDED.is_active,
               sort_order = EXCLUDED.sort_order,
               remark = EXCLUDED.remark,
               updated_at = now()
        """
    )

    op.execute(
        """
        WITH option_seed(product_kind, def_code, option_code, option_name, sort_order) AS (
            VALUES
                ('OTHER', 'MODEL', 'STANDARD', '标准款', 10),
                ('OTHER', 'MODEL', 'BASIC', '基础款', 20),
                ('OTHER', 'MODEL', 'PRO', '专业款', 30),
                ('OTHER', 'MODEL', 'CUSTOM', '定制/特殊型号', 40),
                ('OTHER', 'MODEL', 'OTHER', '其他', 90),

                ('OTHER', 'MATERIAL', 'PAPER', '纸质', 10),
                ('OTHER', 'MATERIAL', 'PLASTIC', '塑料', 20),
                ('OTHER', 'MATERIAL', 'METAL', '金属', 30),
                ('OTHER', 'MATERIAL', 'WOOD', '木质', 40),
                ('OTHER', 'MATERIAL', 'FABRIC', '织物', 50),
                ('OTHER', 'MATERIAL', 'LEATHER', '皮革', 60),
                ('OTHER', 'MATERIAL', 'CERAMIC', '陶瓷', 70),
                ('OTHER', 'MATERIAL', 'GLASS', '玻璃', 80),
                ('OTHER', 'MATERIAL', 'RUBBER', '橡胶', 90),
                ('OTHER', 'MATERIAL', 'OTHER', '其他', 100),

                ('OTHER', 'COLOR', 'BLACK', '黑色', 10),
                ('OTHER', 'COLOR', 'WHITE', '白色', 20),
                ('OTHER', 'COLOR', 'RED', '红色', 30),
                ('OTHER', 'COLOR', 'BLUE', '蓝色', 40),
                ('OTHER', 'COLOR', 'GREEN', '绿色', 50),
                ('OTHER', 'COLOR', 'YELLOW', '黄色', 60),
                ('OTHER', 'COLOR', 'GRAY', '灰色', 70),
                ('OTHER', 'COLOR', 'BROWN', '棕色', 80),
                ('OTHER', 'COLOR', 'PINK', '粉色', 90),
                ('OTHER', 'COLOR', 'MIXED', '混色', 100),
                ('OTHER', 'COLOR', 'OTHER', '其他', 110),

                ('OTHER', 'SIZE', 'XS', '超小', 10),
                ('OTHER', 'SIZE', 'S', '小', 20),
                ('OTHER', 'SIZE', 'M', '中', 30),
                ('OTHER', 'SIZE', 'L', '大', 40),
                ('OTHER', 'SIZE', 'XL', '超大', 50),
                ('OTHER', 'SIZE', 'CUSTOM', '定制/特殊规格', 60),

                ('OTHER', 'USAGE', 'OFFICE', '办公', 10),
                ('OTHER', 'USAGE', 'HOME', '家用', 20),
                ('OTHER', 'USAGE', 'OUTDOOR', '户外', 30),
                ('OTHER', 'USAGE', 'PET', '宠物', 40),
                ('OTHER', 'USAGE', 'CLEANING', '清洁', 50),
                ('OTHER', 'USAGE', 'STORAGE', '收纳', 60),
                ('OTHER', 'USAGE', 'TOOL', '工具', 70),
                ('OTHER', 'USAGE', 'OTHER', '其他', 90)
        )
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
            s.option_code,
            s.option_name,
            TRUE,
            FALSE,
            s.sort_order
        FROM option_seed s
        JOIN item_attribute_defs d
          ON d.product_kind = s.product_kind
         AND d.code = s.def_code
        ON CONFLICT (attribute_def_id, option_code) DO UPDATE
           SET option_name = EXCLUDED.option_name,
               is_active = TRUE,
               sort_order = EXCLUDED.sort_order,
               updated_at = now()
        """
    )


def downgrade() -> None:
    """Remove seeded COMMON / OTHER PMS item attribute templates and options."""

    op.execute(
        """
        DELETE FROM item_attribute_values
        WHERE attribute_def_id IN (
            SELECT id
            FROM item_attribute_defs
            WHERE (product_kind = 'COMMON' AND code IN ('ORIGIN', 'MANUFACTURER', 'SERIES', 'REMARK'))
               OR (product_kind = 'OTHER' AND code IN ('MODEL', 'MATERIAL', 'COLOR', 'SIZE', 'USAGE'))
        )
        """
    )

    op.execute(
        """
        DELETE FROM item_attribute_options
        WHERE attribute_def_id IN (
            SELECT id
            FROM item_attribute_defs
            WHERE (product_kind = 'COMMON' AND code IN ('ORIGIN', 'MANUFACTURER', 'SERIES', 'REMARK'))
               OR (product_kind = 'OTHER' AND code IN ('MODEL', 'MATERIAL', 'COLOR', 'SIZE', 'USAGE'))
        )
        """
    )

    op.execute(
        """
        DELETE FROM item_attribute_defs
        WHERE (product_kind = 'COMMON' AND code IN ('ORIGIN', 'MANUFACTURER', 'SERIES', 'REMARK'))
           OR (product_kind = 'OTHER' AND code IN ('MODEL', 'MATERIAL', 'COLOR', 'SIZE', 'USAGE'))
        """
    )
