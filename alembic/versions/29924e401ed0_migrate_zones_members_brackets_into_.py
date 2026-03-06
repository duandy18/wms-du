"""migrate zones members brackets into level3 tables

Revision ID: 29924e401ed0
Revises: c50075adba75
Create Date: 2026-03-06

旧结构迁移到 Level-3：

zones                -> destination_groups
zone_members         -> destination_group_members
zone_brackets        -> pricing_matrix

注意：
- 本迁移只迁数据，不删除旧表
- 只迁 province 级 members
- 迁移后做 fail-fast 校验
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "29924e401ed0"
down_revision: Union[str, Sequence[str], None] = "c50075adba75"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # =========================================================
    # 1 zones -> destination_groups
    # =========================================================

    op.execute(
        """
        INSERT INTO shipping_provider_destination_groups (
            scheme_id,
            name,
            active,
            created_at,
            updated_at
        )
        SELECT
            z.scheme_id,
            z.name,
            z.active,
            z.created_at,
            z.updated_at
        FROM shipping_provider_zones z
        ON CONFLICT (scheme_id, name) DO NOTHING
        """
    )

    # =========================================================
    # 2 zone_members -> destination_group_members
    #
    # 只迁 province
    # =========================================================

    op.execute(
        """
        INSERT INTO shipping_provider_destination_group_members (
            group_id,
            scope,
            province_name,
            city_name,
            created_at
        )
        SELECT
            dg.id AS group_id,
            'province' AS scope,
            zm.value AS province_name,
            NULL AS city_name,
            zm.created_at
        FROM shipping_provider_zone_members zm
        JOIN shipping_provider_zones z
          ON z.id = zm.zone_id
        JOIN shipping_provider_destination_groups dg
          ON dg.scheme_id = z.scheme_id
         AND dg.name = z.name
        WHERE lower(zm.level) = 'province'
        ON CONFLICT DO NOTHING
        """
    )

    # =========================================================
    # 3 zone_brackets -> pricing_matrix
    # =========================================================

    op.execute(
        """
        INSERT INTO shipping_provider_pricing_matrix (
            group_id,
            min_kg,
            max_kg,
            pricing_mode,
            flat_amount,
            base_amount,
            rate_per_kg,
            base_kg,
            active,
            created_at,
            updated_at
        )
        SELECT
            dg.id AS group_id,
            zb.min_kg,
            zb.max_kg,
            zb.pricing_mode,
            zb.flat_amount,
            zb.base_amount,
            zb.rate_per_kg,
            zb.base_kg,
            zb.active,
            zb.created_at,
            zb.updated_at
        FROM shipping_provider_zone_brackets zb
        JOIN shipping_provider_zones z
          ON z.id = zb.zone_id
        JOIN shipping_provider_destination_groups dg
          ON dg.scheme_id = z.scheme_id
         AND dg.name = z.name
        ON CONFLICT DO NOTHING
        """
    )

    # =========================================================
    # 4 fail-fast 校验
    # =========================================================

    # province members 数量校验

    op.execute(
        """
        DO $$
        DECLARE
            old_n integer;
            new_n integer;
        BEGIN
            SELECT count(*)
              INTO old_n
            FROM shipping_provider_zone_members
            WHERE lower(level) = 'province';

            SELECT count(*)
              INTO new_n
            FROM shipping_provider_destination_group_members
            WHERE scope = 'province';

            IF old_n <> new_n THEN
                RAISE EXCEPTION
                  'province members migration mismatch: old=% new=%',
                  old_n, new_n;
            END IF;
        END $$;
        """
    )

    # brackets 数量校验

    op.execute(
        """
        DO $$
        DECLARE
            old_n integer;
            new_n integer;
        BEGIN
            SELECT count(*) INTO old_n
            FROM shipping_provider_zone_brackets;

            SELECT count(*) INTO new_n
            FROM shipping_provider_pricing_matrix;

            IF old_n <> new_n THEN
                RAISE EXCEPTION
                  'pricing matrix migration mismatch: old=% new=%',
                  old_n, new_n;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """
    回滚策略：

    - 删除新表数据
    - 不恢复旧结构（旧表仍在）
    """

    op.execute("DELETE FROM shipping_provider_pricing_matrix")
    op.execute("DELETE FROM shipping_provider_destination_group_members")
    op.execute("DELETE FROM shipping_provider_destination_groups")
