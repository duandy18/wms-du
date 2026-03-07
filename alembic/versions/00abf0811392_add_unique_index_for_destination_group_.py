"""add_unique_index_for_destination_group_members

Revision ID: 00abf0811392
Revises: 5cf5f577cf96
Create Date: 2026-03-07 14:33:59.718649
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "00abf0811392"
down_revision: Union[str, Sequence[str], None] = "5cf5f577cf96"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


IDX = "uq_spdgm_group_scope_key"
TABLE = "shipping_provider_destination_group_members"


def upgrade() -> None:

    conn = op.get_bind()

    # 防止已有脏数据
    dup = conn.execute(
        sa.text(
            f"""
            SELECT
                group_id,
                scope,
                COALESCE(province_code,'') AS province_code_key,
                COALESCE(city_code,'') AS city_code_key,
                COALESCE(province_name,'') AS province_name_key,
                COALESCE(city_name,'') AS city_name_key,
                COUNT(*) AS n
            FROM {TABLE}
            GROUP BY
                group_id,
                scope,
                COALESCE(province_code,''),
                COALESCE(city_code,''),
                COALESCE(province_name,''),
                COALESCE(city_name,'')
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()

    if dup:
        raise RuntimeError(
            "duplicate destination_group_members rows detected; "
            "clean duplicates before applying unique index"
        )

    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {IDX}
        ON {TABLE} (
            group_id,
            scope,
            COALESCE(province_code,''),
            COALESCE(city_code,''),
            COALESCE(province_name,''),
            COALESCE(city_name,'')
        )
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {IDX}")
