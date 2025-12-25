"""prune_bracket_pricing_to_lookup_model

Revision ID: 7c9cc1182cf6
Revises: 0093b5cac184
Create Date: 2025-12-20 16:41:00.505141

目标（不兼容收敛）：
- shipping_provider_zone_brackets 只保留“查表模型”需要的字段：
  pricing_mode ∈ {flat, linear_total, manual_quote}
  flat_amount, base_amount(面单费/基础费), rate_per_kg
- 删除 legacy 字段：
  pricing_kind, price_json, base_kg, rounding_mode, rounding_step_kg
- 添加 CHECK 约束防呆：
  - flat -> flat_amount 必填
  - linear_total -> rate_per_kg 必填（base_amount 可为空，升级时统一为 0）

注意：此迁移会强制将历史/脏的 pricing_mode 收敛到新三元组，不考虑兼容。
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c9cc1182cf6"
down_revision: Union[str, Sequence[str], None] = "0093b5cac184"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_zone_brackets"

CK_MODE_VALID = "ck_spzb_mode_valid"
CK_FLAT_NEEDS_AMOUNT = "ck_spzb_flat_needs_flat_amount"
CK_LINEAR_NEEDS_RATE = "ck_spzb_linear_needs_rate"


def upgrade() -> None:
    # 0) 先做 normalize：trim + lower，消灭大小写/空格脏值
    op.execute(
        f"""
        UPDATE {TABLE}
        SET pricing_mode = NULLIF(lower(trim(pricing_mode)), '')
        WHERE pricing_mode IS NOT NULL
        """
    )

    # 1) 将已知 legacy 值强制收敛（不兼容策略）
    # per_kg -> linear_total
    op.execute(
        f"""
        UPDATE {TABLE}
        SET pricing_mode = 'linear_total'
        WHERE pricing_mode = 'per_kg'
        """
    )

    # step_over -> linear_total（如果没有 rate_per_kg，就落到 manual_quote）
    op.execute(
        f"""
        UPDATE {TABLE}
        SET pricing_mode = CASE
            WHEN rate_per_kg IS NOT NULL THEN 'linear_total'
            ELSE 'manual_quote'
        END
        WHERE pricing_mode = 'step_over'
        """
    )

    # 常见脏别名 -> manual_quote
    op.execute(
        f"""
        UPDATE {TABLE}
        SET pricing_mode = 'manual_quote'
        WHERE pricing_mode IN ('manual', 'manualrequired', 'manual_required', 'manual-quote')
        """
    )

    # 2) 对 NULL 或未知值：用字段推断（flat_amount / rate_per_kg 优先）
    # 先处理 NULL
    op.execute(
        f"""
        UPDATE {TABLE}
        SET pricing_mode = CASE
            WHEN flat_amount IS NOT NULL THEN 'flat'
            WHEN rate_per_kg IS NOT NULL THEN 'linear_total'
            ELSE 'manual_quote'
        END
        WHERE pricing_mode IS NULL
        """
    )

    # 再处理未知（不在三元组内的残余）
    op.execute(
        f"""
        UPDATE {TABLE}
        SET pricing_mode = CASE
            WHEN flat_amount IS NOT NULL THEN 'flat'
            WHEN rate_per_kg IS NOT NULL THEN 'linear_total'
            ELSE 'manual_quote'
        END
        WHERE pricing_mode NOT IN ('flat','linear_total','manual_quote')
        """
    )

    # 3) linear_total 下 base_amount 允许为空，但我们统一成 0，避免后续计算/展示出现 None
    op.execute(
        f"""
        UPDATE {TABLE}
        SET base_amount = COALESCE(base_amount, 0)
        WHERE pricing_mode = 'linear_total'
        """
    )

    # 4) pricing_mode 改为 NOT NULL + 默认值
    op.alter_column(
        TABLE,
        "pricing_mode",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default="flat",
    )

    # 5) 删除 legacy 列
    op.drop_column(TABLE, "rounding_step_kg")
    op.drop_column(TABLE, "rounding_mode")
    op.drop_column(TABLE, "base_kg")
    op.drop_column(TABLE, "price_json")
    op.drop_column(TABLE, "pricing_kind")

    # 6) 添加 CHECK 约束
    op.create_check_constraint(
        CK_MODE_VALID,
        TABLE,
        "pricing_mode IN ('flat','linear_total','manual_quote')",
    )
    op.create_check_constraint(
        CK_FLAT_NEEDS_AMOUNT,
        TABLE,
        "(pricing_mode <> 'flat') OR (flat_amount IS NOT NULL)",
    )
    op.create_check_constraint(
        CK_LINEAR_NEEDS_RATE,
        TABLE,
        "(pricing_mode <> 'linear_total') OR (rate_per_kg IS NOT NULL)",
    )


def downgrade() -> None:
    # 1) 删除 CHECK 约束
    op.drop_constraint(CK_LINEAR_NEEDS_RATE, TABLE, type_="check")
    op.drop_constraint(CK_FLAT_NEEDS_AMOUNT, TABLE, type_="check")
    op.drop_constraint(CK_MODE_VALID, TABLE, type_="check")

    # 2) 恢复 legacy 列（不回填历史数据）
    op.add_column(TABLE, sa.Column("pricing_kind", sa.String(length=32), nullable=False, server_default="flat"))
    op.add_column(
        TABLE,
        sa.Column(
            "price_json",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(TABLE, sa.Column("base_kg", sa.Numeric(10, 3), nullable=True))
    op.add_column(TABLE, sa.Column("rounding_mode", sa.String(length=16), nullable=True))
    op.add_column(TABLE, sa.Column("rounding_step_kg", sa.Numeric(10, 3), nullable=True))

    # 3) pricing_mode 还原为可空（回到 Phase4“全部 nullable”的平滑态）
    op.alter_column(TABLE, "pricing_mode", existing_type=sa.String(length=32), nullable=True, server_default=None)
