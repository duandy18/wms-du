"""shipping_provider_surcharges_drop_json_and_use_structured_columns

Revision ID: 319c06189882
Revises: af6a74884af8
Create Date: 2026-03-06

目标：
- 为 shipping_provider_surcharges 补齐终态结构列：
    scope
    province_code
    city_code
    province_name
    city_name
    fixed_amount
    rate_per_kg
    percent_rate
- 将现有 surcharge 数据收口到结构化列
- 删除旧 JSON 字段：
    condition_json
    amount_json

说明：
- 本迁移假设当前 surcharge 已处于“结构增强阶段”，已存在：
    priority
    condition_kind
    amount_kind
    stackable
- 对由 dest_adjustments 迁移来的数据（source=dest_adjustments_migration），
  会按 name 前缀 + condition_json/amount_json 回填结构列。
- 对其他非地理 surcharge，默认收口为：
    scope='always'
- 本迁移不做“兼容双轨”，迁移完成后 JSON 彻底退出。
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "319c06189882"
down_revision: Union[str, Sequence[str], None] = "af6a74884af8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_surcharges"


def upgrade() -> None:
    # 1) 先补终态结构列（nullable first，便于回填）
    op.add_column(
        TABLE,
        sa.Column(
            "scope",
            sa.String(length=16),
            nullable=True,
            server_default=sa.text("'always'"),
        ),
    )
    op.add_column(TABLE, sa.Column("province_code", sa.String(length=32), nullable=True))
    op.add_column(TABLE, sa.Column("city_code", sa.String(length=32), nullable=True))
    op.add_column(TABLE, sa.Column("province_name", sa.String(length=64), nullable=True))
    op.add_column(TABLE, sa.Column("city_name", sa.String(length=64), nullable=True))

    op.add_column(TABLE, sa.Column("fixed_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column(TABLE, sa.Column("rate_per_kg", sa.Numeric(12, 4), nullable=True))
    op.add_column(TABLE, sa.Column("percent_rate", sa.Numeric(12, 4), nullable=True))

    # 2) 回填 scope（先给全量默认值）
    op.execute(
        f"""
        UPDATE {TABLE}
        SET scope = 'always'
        WHERE scope IS NULL OR BTRIM(scope) = '';
        """
    )

    # 3) 对“由 dest_adjustments 迁移来的 surcharge”回填地理结构列
    #    name 形如：
    #      DA:province:620000
    #      DA:city:440000:440300
    #
    #    condition_json 形如：
    #      {{"dest":{{"scope":"province","province":"甘肃省"}},"source":"dest_adjustments_migration"}}
    #      {{"dest":{{"scope":"city","province":"广东省","city":"深圳市"}},"source":"dest_adjustments_migration"}}
    #
    #    amount_json 形如：
    #      {{"kind":"flat","amount":0.20}}
    op.execute(
        f"""
        UPDATE {TABLE}
        SET
            scope = CASE
                WHEN name LIKE 'DA:province:%' THEN 'province'
                WHEN name LIKE 'DA:city:%' THEN 'city'
                ELSE scope
            END,
            province_code = CASE
                WHEN name LIKE 'DA:province:%'
                    THEN split_part(name, ':', 3)
                WHEN name LIKE 'DA:city:%'
                    THEN split_part(name, ':', 3)
                ELSE province_code
            END,
            city_code = CASE
                WHEN name LIKE 'DA:city:%'
                    THEN NULLIF(split_part(name, ':', 4), '')
                ELSE city_code
            END,
            province_name = COALESCE(
                NULLIF(condition_json #>> '{{dest,province}}', ''),
                province_name
            ),
            city_name = COALESCE(
                NULLIF(condition_json #>> '{{dest,city}}', ''),
                city_name
            ),
            fixed_amount = CASE
                WHEN lower(COALESCE(amount_json->>'kind', 'flat')) = 'flat'
                    THEN COALESCE((amount_json->>'amount')::numeric, 0)
                ELSE fixed_amount
            END,
            rate_per_kg = CASE
                WHEN lower(COALESCE(amount_json->>'kind', '')) = 'per_kg'
                    THEN COALESCE((amount_json->>'rate_per_kg')::numeric, 0)
                ELSE rate_per_kg
            END,
            percent_rate = CASE
                WHEN lower(COALESCE(amount_json->>'kind', '')) = 'percent'
                    THEN COALESCE((amount_json->>'percent_rate')::numeric, 0)
                ELSE percent_rate
            END
        WHERE condition_json->>'source' = 'dest_adjustments_migration';
        """
    )

    # 4) 对非迁移数据，也尽量把金额类型回填到结构列
    op.execute(
        f"""
        UPDATE {TABLE}
        SET fixed_amount = COALESCE((amount_json->>'amount')::numeric, fixed_amount)
        WHERE lower(COALESCE(amount_json->>'kind', 'flat')) = 'flat'
          AND fixed_amount IS NULL;
        """
    )

    op.execute(
        f"""
        UPDATE {TABLE}
        SET rate_per_kg = COALESCE((amount_json->>'rate_per_kg')::numeric, rate_per_kg)
        WHERE lower(COALESCE(amount_json->>'kind', '')) = 'per_kg'
          AND rate_per_kg IS NULL;
        """
    )

    op.execute(
        f"""
        UPDATE {TABLE}
        SET percent_rate = COALESCE((amount_json->>'percent_rate')::numeric, percent_rate)
        WHERE lower(COALESCE(amount_json->>'kind', '')) = 'percent'
          AND percent_rate IS NULL;
        """
    )

    # 5) 根据旧语义列，尽量规范 scope / amount_kind
    op.execute(
        f"""
        UPDATE {TABLE}
        SET scope = CASE
            WHEN condition_kind IN ('province_name', 'province_code') THEN 'province'
            WHEN condition_kind IN ('city_name', 'city_code') THEN 'city'
            ELSE 'always'
        END
        WHERE scope IS NULL
           OR scope = 'always';
        """
    )

    op.execute(
        f"""
        UPDATE {TABLE}
        SET amount_kind = CASE
            WHEN amount_kind IN ('fixed', 'per_kg', 'percent') THEN amount_kind
            ELSE 'fixed'
        END;
        """
    )

    # 6) 护栏：scope 设为 NOT NULL
    op.alter_column(
        TABLE,
        "scope",
        existing_type=sa.String(length=16),
        nullable=False,
        server_default=sa.text("'always'"),
    )

    # 7) 删除旧 JSON 双轨字段
    op.drop_column(TABLE, "condition_json")
    op.drop_column(TABLE, "amount_json")


def downgrade() -> None:
    # 1) 恢复 JSON 字段（先 nullable=False + default，避免回退时炸）
    op.add_column(
        TABLE,
        sa.Column(
            "condition_json",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "amount_json",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # 2) 用结构列尽量回填 JSON
    op.execute(
        f"""
        UPDATE {TABLE}
        SET condition_json = CASE
            WHEN scope = 'province' THEN jsonb_build_object(
                'dest', jsonb_build_object(
                    'scope', 'province',
                    'province', COALESCE(province_name, '')
                )
            )
            WHEN scope = 'city' THEN jsonb_build_object(
                'dest', jsonb_build_object(
                    'scope', 'city',
                    'province', COALESCE(province_name, ''),
                    'city', COALESCE(city_name, '')
                )
            )
            ELSE '{{}}'::jsonb
        END;
        """
    )

    op.execute(
        f"""
        UPDATE {TABLE}
        SET amount_json = CASE
            WHEN amount_kind = 'per_kg' THEN jsonb_build_object(
                'kind', 'per_kg',
                'rate_per_kg', COALESCE(rate_per_kg, 0)
            )
            WHEN amount_kind = 'percent' THEN jsonb_build_object(
                'kind', 'percent',
                'percent_rate', COALESCE(percent_rate, 0)
            )
            ELSE jsonb_build_object(
                'kind', 'flat',
                'amount', COALESCE(fixed_amount, 0)
            )
        END;
        """
    )

    # 3) 删除终态结构列
    op.drop_column(TABLE, "percent_rate")
    op.drop_column(TABLE, "rate_per_kg")
    op.drop_column(TABLE, "fixed_amount")

    op.drop_column(TABLE, "city_name")
    op.drop_column(TABLE, "province_name")
    op.drop_column(TABLE, "city_code")
    op.drop_column(TABLE, "province_code")
    op.drop_column(TABLE, "scope")
