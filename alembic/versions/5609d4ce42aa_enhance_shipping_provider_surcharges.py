"""enhance_shipping_provider_surcharges

Revision ID: 5609d4ce42aa
Revises: 97ed70677b6f
Create Date: 2026-03-06 11:54:16.090129

目标：
- 为 shipping_provider_surcharges 增加终态增强字段：
  priority / condition_kind / amount_kind / stackable
- 回填现有 surcharge 数据
- 为后续接收 pricing_scheme_dest_adjustments 铺路
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5609d4ce42aa"
down_revision: Union[str, Sequence[str], None] = "97ed70677b6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_surcharges"


def upgrade() -> None:
    # 1) 新列（先带默认值，避免历史数据为空）
    op.add_column(
        TABLE,
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
    )
    op.add_column(
        TABLE,
        sa.Column("condition_kind", sa.String(length=32), nullable=False, server_default=sa.text("'always'")),
    )
    op.add_column(
        TABLE,
        sa.Column("amount_kind", sa.String(length=32), nullable=False, server_default=sa.text("'fixed'")),
    )
    op.add_column(
        TABLE,
        sa.Column("stackable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    # 2) 回填 condition_kind
    # 规则：
    # - 有 dest.scope=province -> province_name
    # - 有 dest.scope=city     -> city_name
    # - 有旧列表 province/city  -> province_name / city_name
    # - 有 flag_any            -> flag_any
    # - 其他                   -> always
    op.execute(
        f"""
        UPDATE {TABLE}
        SET condition_kind = CASE
            WHEN jsonb_typeof(condition_json) = 'object'
                 AND jsonb_typeof(condition_json->'dest') = 'object'
                 AND lower(coalesce(condition_json->'dest'->>'scope', '')) = 'city'
              THEN 'city_name'
            WHEN jsonb_typeof(condition_json) = 'object'
                 AND jsonb_typeof(condition_json->'dest') = 'object'
                 AND lower(coalesce(condition_json->'dest'->>'scope', '')) = 'province'
              THEN 'province_name'
            WHEN jsonb_typeof(condition_json) = 'object'
                 AND jsonb_typeof(condition_json->'dest') = 'object'
                 AND jsonb_typeof(condition_json->'dest'->'city') = 'array'
                 AND jsonb_array_length(condition_json->'dest'->'city') > 0
              THEN 'city_name'
            WHEN jsonb_typeof(condition_json) = 'object'
                 AND jsonb_typeof(condition_json->'dest') = 'object'
                 AND jsonb_typeof(condition_json->'dest'->'province') = 'array'
                 AND jsonb_array_length(condition_json->'dest'->'province') > 0
              THEN 'province_name'
            WHEN jsonb_typeof(condition_json) = 'object'
                 AND jsonb_typeof(condition_json->'flag_any') = 'array'
                 AND jsonb_array_length(condition_json->'flag_any') > 0
              THEN 'flag_any'
            ELSE 'always'
        END
        """
    )

    # 3) 回填 amount_kind
    # - flat   -> fixed
    # - per_kg -> per_kg
    # - table  -> table
    # - 其他   -> fixed
    op.execute(
        f"""
        UPDATE {TABLE}
        SET amount_kind = CASE lower(coalesce(amount_json->>'kind', 'flat'))
            WHEN 'flat' THEN 'fixed'
            WHEN 'per_kg' THEN 'per_kg'
            WHEN 'table' THEN 'table'
            ELSE 'fixed'
        END
        """
    )

    # 4) CHECK 约束
    op.create_check_constraint(
        "ck_sp_surcharges_condition_kind",
        TABLE,
        "condition_kind IN ('always', 'province_name', 'city_name', 'province_code', 'city_code', 'flag_any', 'weight_gte', 'weight_lt')",
    )
    op.create_check_constraint(
        "ck_sp_surcharges_amount_kind",
        TABLE,
        "amount_kind IN ('fixed', 'per_kg', 'table', 'percent')",
    )

    # 5) 查询索引
    op.create_index(
        "ix_sp_surcharges_scheme_active_priority",
        TABLE,
        ["scheme_id", "active", "priority"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sp_surcharges_scheme_active_priority", table_name=TABLE)

    op.drop_constraint("ck_sp_surcharges_amount_kind", TABLE, type_="check")
    op.drop_constraint("ck_sp_surcharges_condition_kind", TABLE, type_="check")

    op.drop_column(TABLE, "stackable")
    op.drop_column(TABLE, "amount_kind")
    op.drop_column(TABLE, "condition_kind")
    op.drop_column(TABLE, "priority")
