"""add_partial_unique_indexes_for_shipping_provider_surcharges

Revision ID: 5cf5f577cf96
Revises: ffa019067b26
Create Date: 2026-03-07 14:15:22.222546

终态强化：
1) active province surcharge 在同一 scheme 内唯一
2) active city surcharge 在同一 scheme 内唯一

说明：
- 这里不处理 province/city 互斥，那是 service 层规则
- 这里处理的是“同 scope、同目标 key 的 active 重复”这件事
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5cf5f577cf96"
down_revision: Union[str, Sequence[str], None] = "ffa019067b26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


IDX_PROV = "uq_sp_surcharges_active_province_key"
IDX_CITY = "uq_sp_surcharges_active_city_key"


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    dup_prov = conn.execute(
        sa.text(
            """
            SELECT
              scheme_id,
              COALESCE(province_code, '') AS province_code_key,
              COALESCE(province_name, '') AS province_name_key,
              COUNT(*) AS n
            FROM shipping_provider_surcharges
            WHERE active IS TRUE
              AND scope = 'province'
            GROUP BY
              scheme_id,
              COALESCE(province_code, ''),
              COALESCE(province_name, '')
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if dup_prov:
        raise RuntimeError(
            "Migration blocked: duplicate active province surcharges exist; "
            "clean data before adding partial unique index"
        )

    dup_city = conn.execute(
        sa.text(
            """
            SELECT
              scheme_id,
              COALESCE(province_code, '') AS province_code_key,
              COALESCE(province_name, '') AS province_name_key,
              COALESCE(city_code, '') AS city_code_key,
              COALESCE(city_name, '') AS city_name_key,
              COUNT(*) AS n
            FROM shipping_provider_surcharges
            WHERE active IS TRUE
              AND scope = 'city'
            GROUP BY
              scheme_id,
              COALESCE(province_code, ''),
              COALESCE(province_name, ''),
              COALESCE(city_code, ''),
              COALESCE(city_name, '')
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if dup_city:
        raise RuntimeError(
            "Migration blocked: duplicate active city surcharges exist; "
            "clean data before adding partial unique index"
        )

    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {IDX_PROV}
        ON shipping_provider_surcharges (
          scheme_id,
          COALESCE(province_code, ''),
          COALESCE(province_name, '')
        )
        WHERE active IS TRUE AND scope = 'province'
        """
    )

    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {IDX_CITY}
        ON shipping_provider_surcharges (
          scheme_id,
          COALESCE(province_code, ''),
          COALESCE(province_name, ''),
          COALESCE(city_code, ''),
          COALESCE(city_name, '')
        )
        WHERE active IS TRUE AND scope = 'city'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(f"DROP INDEX IF EXISTS {IDX_CITY}")
    op.execute(f"DROP INDEX IF EXISTS {IDX_PROV}")
