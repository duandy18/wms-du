"""shrink shipping provider surcharges to fixed-only

Revision ID: 56b52937bf0f
Revises: a708e27b5d0d
Create Date: 2026-03-06 14:59:47.255472

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "56b52937bf0f"
down_revision: Union[str, Sequence[str], None] = "a708e27b5d0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_surcharges"

OLD_AMOUNT_FIELDS_CK = "ck_sp_surcharges_amount_fields"
OLD_AMOUNT_KIND_CK = "ck_sp_surcharges_amount_kind"
NEW_FIXED_CK = "ck_sp_surcharges_fixed_amount_required"


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    sql = sa.text(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = :table_name
           AND column_name = :column_name
         LIMIT 1
        """
    )
    return bind.execute(
        sql,
        {"table_name": table_name, "column_name": column_name},
    ).scalar() is not None


def upgrade() -> None:
    """
    收口附加费结构：

    旧结构：
        amount_kind = fixed / per_kg / percent
        fixed_amount
        rate_per_kg
        percent_rate

    新结构：
        只保留 fixed_amount
    """

    # 1) 先把 fixed_amount 补齐，避免后续改 NOT NULL 时翻车
    op.execute(
        """
        UPDATE shipping_provider_surcharges
           SET fixed_amount = COALESCE(fixed_amount, 0)
         WHERE fixed_amount IS NULL
        """
    )

    # 2) 老约束幂等删除：不用 DO $$，直接显式 DDL
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {OLD_AMOUNT_FIELDS_CK}")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {OLD_AMOUNT_KIND_CK}")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {NEW_FIXED_CK}")

    # 3) 删历史列（同样做存在判断）
    if _column_exists(TABLE, "rate_per_kg"):
        op.drop_column(TABLE, "rate_per_kg")

    if _column_exists(TABLE, "percent_rate"):
        op.drop_column(TABLE, "percent_rate")

    if _column_exists(TABLE, "amount_kind"):
        op.drop_column(TABLE, "amount_kind")

    # 4) fixed_amount 改为 NOT NULL
    op.alter_column(
        TABLE,
        "fixed_amount",
        existing_type=sa.Numeric(12, 2),
        nullable=False,
    )

    # 5) 新约束：fixed_amount 必须存在且 >= 0
    op.create_check_constraint(
        NEW_FIXED_CK,
        TABLE,
        "fixed_amount >= 0",
    )


def downgrade() -> None:
    """
    回滚到旧结构：
        amount_kind = fixed / per_kg / percent
        fixed_amount / rate_per_kg / percent_rate
    """

    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {NEW_FIXED_CK}")

    op.alter_column(
        TABLE,
        "fixed_amount",
        existing_type=sa.Numeric(12, 2),
        nullable=True,
    )

    if not _column_exists(TABLE, "amount_kind"):
        op.add_column(
            TABLE,
            sa.Column(
                "amount_kind",
                sa.String(length=32),
                nullable=False,
                server_default="fixed",
            ),
        )

    if not _column_exists(TABLE, "rate_per_kg"):
        op.add_column(
            TABLE,
            sa.Column(
                "rate_per_kg",
                sa.Numeric(12, 4),
                nullable=True,
            ),
        )

    if not _column_exists(TABLE, "percent_rate"):
        op.add_column(
            TABLE,
            sa.Column(
                "percent_rate",
                sa.Numeric(12, 4),
                nullable=True,
            ),
        )

    # 回滚后统一恢复为 fixed 形态，保证旧约束能建立
    op.execute(
        """
        UPDATE shipping_provider_surcharges
           SET amount_kind = 'fixed',
               rate_per_kg = NULL,
               percent_rate = NULL,
               fixed_amount = COALESCE(fixed_amount, 0)
        """
    )

    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {OLD_AMOUNT_KIND_CK}")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {OLD_AMOUNT_FIELDS_CK}")

    op.create_check_constraint(
        OLD_AMOUNT_KIND_CK,
        TABLE,
        "amount_kind in ('fixed','per_kg','percent')",
    )

    op.create_check_constraint(
        OLD_AMOUNT_FIELDS_CK,
        TABLE,
        """
        (
          (amount_kind = 'fixed'
            AND fixed_amount IS NOT NULL
            AND rate_per_kg IS NULL
            AND percent_rate IS NULL
          )
          OR
          (amount_kind = 'per_kg'
            AND fixed_amount IS NULL
            AND rate_per_kg IS NOT NULL
            AND percent_rate IS NULL
          )
          OR
          (amount_kind = 'percent'
            AND fixed_amount IS NULL
            AND rate_per_kg IS NULL
            AND percent_rate IS NOT NULL
          )
        )
        """,
    )
