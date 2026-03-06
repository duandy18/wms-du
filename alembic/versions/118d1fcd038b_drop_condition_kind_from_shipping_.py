"""drop_condition_kind_from_shipping_provider_surcharges.

Revision ID: 118d1fcd038b
Revises: 56b52937bf0f
Create Date: 2026-03-06 15:59:19.161609

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "118d1fcd038b"
down_revision: Union[str, Sequence[str], None] = "56b52937bf0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_surcharges"

OLD_CONDITION_KIND_CK = "ck_sp_surcharges_condition_kind"

NEW_SCOPE_VALID_CK = "ck_sp_surcharges_scope_valid"
NEW_SCOPE_FIELDS_CK = "ck_sp_surcharges_scope_fields"


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
    surcharge 终态收口：

    删除历史残影：
        condition_kind

    新终态：
        scope + province/city fields + fixed_amount
    """

    # 1 删除旧约束
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {OLD_CONDITION_KIND_CK}")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {NEW_SCOPE_VALID_CK}")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {NEW_SCOPE_FIELDS_CK}")

    # 2 删除历史列
    if _column_exists(TABLE, "condition_kind"):
        op.drop_column(TABLE, "condition_kind")

    # 3 新终态约束：scope 合法
    op.create_check_constraint(
        NEW_SCOPE_VALID_CK,
        TABLE,
        "scope in ('always','province','city')",
    )

    # 4 新终态约束：scope 与字段语义一致
    op.create_check_constraint(
        NEW_SCOPE_FIELDS_CK,
        TABLE,
        """
        (
          (scope = 'always'
            AND province_name IS NULL
            AND city_name IS NULL
            AND province_code IS NULL
            AND city_code IS NULL
          )
          OR
          (scope = 'province'
            AND (province_name IS NOT NULL OR province_code IS NOT NULL)
            AND city_name IS NULL
            AND city_code IS NULL
          )
          OR
          (scope = 'city'
            AND (province_name IS NOT NULL OR province_code IS NOT NULL)
            AND (city_name IS NOT NULL OR city_code IS NOT NULL)
          )
        )
        """,
    )


def downgrade() -> None:
    """
    回滚：

    恢复 condition_kind
    """

    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {NEW_SCOPE_FIELDS_CK}")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {NEW_SCOPE_VALID_CK}")

    if not _column_exists(TABLE, "condition_kind"):
        op.add_column(
            TABLE,
            sa.Column(
                "condition_kind",
                sa.String(length=32),
                nullable=False,
                server_default="always",
            ),
        )

    # 用 scope 回填 condition_kind
    op.execute(
        f"""
        UPDATE {TABLE}
           SET condition_kind =
               CASE
                   WHEN scope = 'always' THEN 'always'
                   WHEN scope = 'province' THEN
                       CASE
                           WHEN province_code IS NOT NULL THEN 'province_code'
                           ELSE 'province_name'
                       END
                   WHEN scope = 'city' THEN
                       CASE
                           WHEN city_code IS NOT NULL THEN 'city_code'
                           ELSE 'city_name'
                       END
                   ELSE 'always'
               END
        """
    )

    op.create_check_constraint(
        OLD_CONDITION_KIND_CK,
        TABLE,
        """
        condition_kind in (
          'always',
          'province_name',
          'city_name',
          'province_code',
          'city_code',
          'flag_any',
          'weight_gte',
          'weight_lt'
        )
        """,
    )
