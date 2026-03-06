"""shipping_provider_surcharges_add_structured_scope_and_amount_columns

Revision ID: a708e27b5d0d
Revises: 319c06189882
Create Date: 2026-03-06 13:06:42.871607

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

说明：
- 仅补结构列 + 尽可能回填
- 不依赖 condition_json / amount_json 必然存在
- 若旧 JSON 列仍存在，则优先从 JSON 回填
- 若旧 JSON 列已不存在，则退化为：
    - 依据 condition_kind 回填 scope
    - 依据 name（如 DA:province:620000 / DA:city:440000:440300）回填 code
    - amount 数值列无法凭空恢复时保持 NULL
- 本迁移不删除任何旧列；只做“补列+回填”
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "a708e27b5d0d"
down_revision: Union[str, Sequence[str], None] = "319c06189882"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_surcharges"


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    insp = inspect(bind)
    return {c["name"] for c in insp.get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    cols = _column_names(table_name)
    if column.name not in cols:
        op.add_column(table_name, column)


def upgrade() -> None:
    # ------------------------------------------------------------
    # 1) 补齐结构列（只加缺失列）
    # ------------------------------------------------------------
    _add_column_if_missing(
        TABLE,
        sa.Column(
            "scope",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'always'"),
        ),
    )
    _add_column_if_missing(TABLE, sa.Column("province_code", sa.String(length=32), nullable=True))
    _add_column_if_missing(TABLE, sa.Column("city_code", sa.String(length=32), nullable=True))
    _add_column_if_missing(TABLE, sa.Column("province_name", sa.String(length=64), nullable=True))
    _add_column_if_missing(TABLE, sa.Column("city_name", sa.String(length=64), nullable=True))
    _add_column_if_missing(TABLE, sa.Column("fixed_amount", sa.Numeric(12, 2), nullable=True))
    _add_column_if_missing(TABLE, sa.Column("rate_per_kg", sa.Numeric(12, 4), nullable=True))
    _add_column_if_missing(TABLE, sa.Column("percent_rate", sa.Numeric(12, 4), nullable=True))

    cols = _column_names(TABLE)
    has_condition_json = "condition_json" in cols
    has_amount_json = "amount_json" in cols
    has_condition_kind = "condition_kind" in cols
    has_name = "name" in cols

    # ------------------------------------------------------------
    # 2) scope 回填
    # ------------------------------------------------------------
    if has_condition_json:
        op.execute(
            sa.text(
                f"""
                UPDATE {TABLE}
                SET scope = CASE
                    WHEN condition_json->'dest'->>'scope' = 'city' THEN 'city'
                    WHEN condition_json->'dest'->>'scope' = 'province' THEN 'province'
                    ELSE COALESCE(scope, 'always')
                END
                """
            )
        )

    if has_condition_kind:
        op.execute(
            sa.text(
                f"""
                UPDATE {TABLE}
                SET scope = CASE
                    WHEN condition_kind IN ('province_name', 'province_code') THEN 'province'
                    WHEN condition_kind IN ('city_name', 'city_code') THEN 'city'
                    ELSE 'always'
                END
                WHERE scope IS NULL OR BTRIM(scope) = '' OR scope = 'always'
                """
            )
        )

    # ------------------------------------------------------------
    # 3) 名称字段回填
    # ------------------------------------------------------------
    if has_condition_json:
        op.execute(
            sa.text(
                f"""
                UPDATE {TABLE}
                SET
                    province_name = COALESCE(province_name, NULLIF(condition_json->'dest'->>'province', '')),
                    city_name = COALESCE(city_name, NULLIF(condition_json->'dest'->>'city', ''))
                """
            )
        )

    # ------------------------------------------------------------
    # 4) code 回填
    #    优先从迁移生成的 name 模式解析：
    #      DA:province:620000
    #      DA:city:440000:440300
    # ------------------------------------------------------------
    if has_name:
        op.execute(
            sa.text(
                f"""
                UPDATE {TABLE}
                SET province_code = split_part(name, ':', 3)
                WHERE (province_code IS NULL OR BTRIM(province_code) = '')
                  AND name LIKE 'DA:province:%'
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                UPDATE {TABLE}
                SET
                    province_code = split_part(name, ':', 3),
                    city_code = NULLIF(split_part(name, ':', 4), '')
                WHERE ((province_code IS NULL OR BTRIM(province_code) = '')
                    OR (city_code IS NULL OR BTRIM(city_code) = ''))
                  AND name LIKE 'DA:city:%'
                """
            )
        )

    # ------------------------------------------------------------
    # 5) amount 数值回填
    #    - 若 amount_json 还在：尽量回填
    #    - 若 amount_json 已不存在：无法从空气里恢复，保持 NULL
    # ------------------------------------------------------------
    if has_amount_json:
        op.execute(
            sa.text(
                f"""
                UPDATE {TABLE}
                SET fixed_amount = (amount_json->>'amount')::numeric
                WHERE (fixed_amount IS NULL)
                  AND lower(COALESCE(amount_json->>'kind', '')) = 'flat'
                  AND (amount_json ? 'amount')
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                UPDATE {TABLE}
                SET rate_per_kg = COALESCE(
                    (amount_json->>'rate_per_kg')::numeric,
                    (amount_json->>'rate')::numeric
                )
                WHERE (rate_per_kg IS NULL)
                  AND lower(COALESCE(amount_json->>'kind', '')) = 'per_kg'
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                UPDATE {TABLE}
                SET percent_rate = COALESCE(
                    (amount_json->>'percent_rate')::numeric,
                    (amount_json->>'percent')::numeric
                )
                WHERE (percent_rate IS NULL)
                  AND lower(COALESCE(amount_json->>'kind', '')) = 'percent'
                """
            )
        )

    # ------------------------------------------------------------
    # 6) 最后清掉 scope 默认值，避免长期默认污染
    # ------------------------------------------------------------
    op.alter_column(
        TABLE,
        "scope",
        existing_type=sa.String(length=16),
        server_default=None,
        existing_nullable=False,
    )


def downgrade() -> None:
    # 只回退这条迁移新增的结构列
    cols = _column_names(TABLE)

    if "percent_rate" in cols:
        op.drop_column(TABLE, "percent_rate")
    if "rate_per_kg" in cols:
        op.drop_column(TABLE, "rate_per_kg")
    if "fixed_amount" in cols:
        op.drop_column(TABLE, "fixed_amount")
    if "city_name" in cols:
        op.drop_column(TABLE, "city_name")
    if "province_name" in cols:
        op.drop_column(TABLE, "province_name")
    if "city_code" in cols:
        op.drop_column(TABLE, "city_code")
    if "province_code" in cols:
        op.drop_column(TABLE, "province_code")
    if "scope" in cols:
        op.drop_column(TABLE, "scope")
