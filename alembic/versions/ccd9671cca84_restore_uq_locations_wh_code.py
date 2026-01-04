"""restore uq_locations_wh_code

Revision ID: ccd9671cca84
Revises: 957cb77d2ab6
Create Date: 2025-11-09 21:49:12.071611
"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ccd9671cca84"
down_revision: Union[str, Sequence[str], None] = "957cb77d2ab6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0) 去重清障（若存在重复 (warehouse_id, code)，只保留每组最小 id）
    op.execute(
        """
        WITH dups AS (
            SELECT MIN(id) AS keep_id, warehouse_id, code
            FROM locations
            GROUP BY warehouse_id, code
            HAVING COUNT(*) > 1
        )
        DELETE FROM locations t
        USING dups d
        WHERE t.warehouse_id = d.warehouse_id
          AND t.code = d.code
          AND t.id <> d.keep_id;
        """
    )

    # 1) 幂等删除可能存在的“同名唯一约束/索引”
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class rel ON rel.oid = c.conrelid
                WHERE c.contype='u' AND c.conname='uq_locations_wh_code'
                  AND rel.relname='locations'
            ) THEN
                EXECUTE 'ALTER TABLE "locations" DROP CONSTRAINT "uq_locations_wh_code"';
            END IF;
        END $$;
        """
    )
    op.execute('DROP INDEX IF EXISTS "ix_locations_wh_code"')

    # 2) 建立唯一约束，满足 ON CONFLICT (warehouse_id, code)
    op.create_unique_constraint(
        "uq_locations_wh_code", "locations", ["warehouse_id", "code"]
    )


def downgrade() -> None:
    # 回滚：删除唯一约束
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class rel ON rel.oid = c.conrelid
                WHERE c.contype='u' AND c.conname='uq_locations_wh_code'
                  AND rel.relname='locations'
            ) THEN
                EXECUTE 'ALTER TABLE "locations" DROP CONSTRAINT "uq_locations_wh_code"';
            END IF;
        END $$;
        """
    )
