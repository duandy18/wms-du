"""phase_shipping_scheme_weight_rules_structured

Revision ID: 06bed84c1140
Revises: 8c2926a02fe8
Create Date: 2026-03-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "06bed84c1140"
down_revision: Union[str, Sequence[str], None] = "8c2926a02fe8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase-2：运价 scheme 结构化计费规则

    改动：
    1 删除 JSON 字段 billable_weight_rule
    2 删除旧 active 字段
    3 新增 lifecycle status
    4 新增结构化计费重量字段
    """

    # ---------- 删除旧字段 ----------
    with op.batch_alter_table("shipping_provider_pricing_schemes") as batch:

        batch.drop_column("billable_weight_rule")
        batch.drop_column("active")

    # ---------- 新增 lifecycle ----------
    with op.batch_alter_table("shipping_provider_pricing_schemes") as batch:

        batch.add_column(
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default="draft",
            )
        )

    # ---------- 新增计费重量字段 ----------
    with op.batch_alter_table("shipping_provider_pricing_schemes") as batch:

        batch.add_column(
            sa.Column(
                "billable_weight_strategy",
                sa.String(length=32),
                nullable=False,
                server_default="actual_only",
            )
        )

        batch.add_column(
            sa.Column(
                "volume_divisor",
                sa.Integer(),
                nullable=True,
            )
        )

        batch.add_column(
            sa.Column(
                "rounding_mode",
                sa.String(length=16),
                nullable=False,
                server_default="none",
            )
        )

        batch.add_column(
            sa.Column(
                "rounding_step_kg",
                sa.Numeric(10, 3),
                nullable=True,
            )
        )

        batch.add_column(
            sa.Column(
                "min_billable_weight_kg",
                sa.Numeric(10, 3),
                nullable=True,
            )
        )

    # ---------- CHECK 约束 ----------
    op.create_check_constraint(
        "ck_spps_status_valid",
        "shipping_provider_pricing_schemes",
        "status in ('draft','active','archived')",
    )

    op.create_check_constraint(
        "ck_spps_billable_strategy",
        "shipping_provider_pricing_schemes",
        "billable_weight_strategy in ('actual_only','max_actual_volume')",
    )

    op.create_check_constraint(
        "ck_spps_rounding_mode",
        "shipping_provider_pricing_schemes",
        "rounding_mode in ('none','ceil')",
    )


def downgrade() -> None:
    """
    回退逻辑（理论上不建议执行）
    """

    with op.batch_alter_table("shipping_provider_pricing_schemes") as batch:

        batch.drop_constraint("ck_spps_rounding_mode", type_="check")
        batch.drop_constraint("ck_spps_billable_strategy", type_="check")
        batch.drop_constraint("ck_spps_status_valid", type_="check")

        batch.drop_column("min_billable_weight_kg")
        batch.drop_column("rounding_step_kg")
        batch.drop_column("rounding_mode")
        batch.drop_column("volume_divisor")
        batch.drop_column("billable_weight_strategy")

        batch.drop_column("status")

        batch.add_column(
            sa.Column(
                "active",
                sa.Boolean(),
                nullable=False,
                server_default="true",
            )
        )

        batch.add_column(
            sa.Column(
                "billable_weight_rule",
                sa.JSON(),
                nullable=True,
            )
        )
