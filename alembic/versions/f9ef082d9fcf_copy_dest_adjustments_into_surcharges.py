"""copy_dest_adjustments_into_surcharges

Revision ID: f9ef082d9fcf
Revises: 5609d4ce42aa
Create Date: 2026-03-06 12:07:22.215178

目标：
- 将 pricing_scheme_dest_adjustments 复制到 shipping_provider_surcharges
- 仅做数据迁移，不删除旧表
- 为后续 calc_quote 主链切到 surcharge-only 做准备
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f9ef082d9fcf"
down_revision: Union[str, Sequence[str], None] = "5609d4ce42aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO shipping_provider_surcharges (
            scheme_id,
            name,
            active,
            priority,
            condition_kind,
            amount_kind,
            stackable,
            condition_json,
            amount_json
        )
        SELECT
            da.scheme_id,
            CASE
                WHEN da.scope = 'province'
                    THEN 'DA:province:' || COALESCE(
                        NULLIF(BTRIM(da.province_code), ''),
                        NULLIF(BTRIM(da.province), ''),
                        da.id::text
                    )
                WHEN da.scope = 'city'
                    THEN 'DA:city:' || COALESCE(
                        NULLIF(BTRIM(da.province_code), ''),
                        NULLIF(BTRIM(da.province), ''),
                        'NA'
                    )
                    || ':' ||
                    COALESCE(
                        NULLIF(BTRIM(da.city_code), ''),
                        NULLIF(BTRIM(da.city), ''),
                        da.id::text
                    )
                ELSE 'DA:unknown:' || da.id::text
            END AS name,
            da.active,
            COALESCE(da.priority, 100) AS priority,
            CASE
                WHEN da.scope = 'province' THEN 'province_name'
                WHEN da.scope = 'city' THEN 'city_name'
                ELSE 'always'
            END AS condition_kind,
            'fixed' AS amount_kind,
            true AS stackable,
            CASE
                WHEN da.scope = 'province' THEN
                    jsonb_build_object(
                        'source', 'dest_adjustments_migration',
                        'dest', jsonb_build_object(
                            'scope', 'province',
                            'province', COALESCE(
                                NULLIF(BTRIM(da.province_name), ''),
                                NULLIF(BTRIM(da.province), ''),
                                NULLIF(BTRIM(da.province_code), '')
                            )
                        )
                    )
                WHEN da.scope = 'city' THEN
                    jsonb_build_object(
                        'source', 'dest_adjustments_migration',
                        'dest', jsonb_build_object(
                            'scope', 'city',
                            'province', COALESCE(
                                NULLIF(BTRIM(da.province_name), ''),
                                NULLIF(BTRIM(da.province), ''),
                                NULLIF(BTRIM(da.province_code), '')
                            ),
                            'city', COALESCE(
                                NULLIF(BTRIM(da.city_name), ''),
                                NULLIF(BTRIM(da.city), ''),
                                NULLIF(BTRIM(da.city_code), '')
                            )
                        )
                    )
                ELSE
                    jsonb_build_object(
                        'source', 'dest_adjustments_migration'
                    )
            END AS condition_json,
            jsonb_build_object(
                'kind', 'flat',
                'amount', da.amount
            ) AS amount_json
        FROM pricing_scheme_dest_adjustments da
        WHERE NOT EXISTS (
            SELECT 1
            FROM shipping_provider_surcharges s
            WHERE s.scheme_id = da.scheme_id
              AND s.name = CASE
                    WHEN da.scope = 'province'
                        THEN 'DA:province:' || COALESCE(
                            NULLIF(BTRIM(da.province_code), ''),
                            NULLIF(BTRIM(da.province), ''),
                            da.id::text
                        )
                    WHEN da.scope = 'city'
                        THEN 'DA:city:' || COALESCE(
                            NULLIF(BTRIM(da.province_code), ''),
                            NULLIF(BTRIM(da.province), ''),
                            'NA'
                        )
                        || ':' ||
                        COALESCE(
                            NULLIF(BTRIM(da.city_code), ''),
                            NULLIF(BTRIM(da.city), ''),
                            da.id::text
                        )
                    ELSE 'DA:unknown:' || da.id::text
                END
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM shipping_provider_surcharges
        WHERE condition_json->>'source' = 'dest_adjustments_migration'
        """
    )
