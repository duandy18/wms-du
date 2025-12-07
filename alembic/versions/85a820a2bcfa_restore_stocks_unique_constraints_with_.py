"""restore stocks unique constraints (with/without batch)

Revision ID: 8b3d2b0f7e21
Revises: 4e7a1b2c3d90
Create Date: 2025-11-09 22:28:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "8b3d2b0f7e21"
down_revision: Union[str, Sequence[str], None] = "4e7a1b2c3d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0) 去重清障：有批次三列唯一；无批次两列唯一（batch_id IS NULL）
    #    规则：对每组保留最小 id 记录
    op.execute(
        """
        -- 有批次：按 (item_id, location_id, batch_id)
        WITH dups AS (
            SELECT MIN(id) AS keep_id, item_id, location_id, batch_id
            FROM stocks
            WHERE batch_id IS NOT NULL
            GROUP BY item_id, location_id, batch_id
            HAVING COUNT(*) > 1
        )
        DELETE FROM stocks t USING dups d
        WHERE t.batch_id IS NOT NULL
          AND t.item_id = d.item_id
          AND t.location_id = d.location_id
          AND t.batch_id = d.batch_id
          AND t.id <> d.keep_id;
        """
    )
    op.execute(
        """
        -- 无批次：按 (item_id, location_id) 且 batch_id IS NULL
        WITH dups AS (
            SELECT MIN(id) AS keep_id, item_id, location_id
            FROM stocks
            WHERE batch_id IS NULL
            GROUP BY item_id, location_id
            HAVING COUNT(*) > 1
        )
        DELETE FROM stocks t USING dups d
        WHERE t.batch_id IS NULL
          AND t.item_id = d.item_id
          AND t.location_id = d.location_id
          AND t.id <> d.keep_id;
        """
    )

    # 1) 幂等清理历史同名对象
    #   - 以前我们用过索引名 uq_stocks_item_loc_batch / uq_stocks_nobatch
    #   - 先删同名唯一约束/索引（如果残留）
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM   pg_constraint c
                JOIN   pg_class rel ON rel.oid = c.conrelid
                WHERE  c.contype='u' AND c.conname='uq_stocks_item_loc_batch'
                   AND rel.relname='stocks'
            ) THEN
                EXECUTE 'ALTER TABLE "stocks" DROP CONSTRAINT "uq_stocks_item_loc_batch"';
            END IF;
        END $$;
        """
    )
    op.execute('DROP INDEX IF EXISTS "uq_stocks_item_loc_batch"')
    op.execute('DROP INDEX IF EXISTS "uq_stocks_nobatch"')

    # 2) 恢复“有批次”唯一约束（可被 ON CONFLICT ON CONSTRAINT 引用）
    op.create_unique_constraint(
        "uq_stocks_item_loc_batch", "stocks", ["item_id", "location_id", "batch_id"]
    )

    # 3) 恢复“无批次”唯一口径：partial unique index（不能做成约束）
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_stocks_nobatch
        ON stocks (item_id, location_id)
        WHERE batch_id IS NULL
        """
    )


def downgrade() -> None:
    # 回滚顺序：先删 partial unique index，再删约束
    op.execute('DROP INDEX IF EXISTS "uq_stocks_nobatch"')
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM   pg_constraint c
                JOIN   pg_class rel ON rel.oid = c.conrelid
                WHERE  c.contype='u' AND c.conname='uq_stocks_item_loc_batch'
                   AND rel.relname='stocks'
            ) THEN
                EXECUTE 'ALTER TABLE "stocks" DROP CONSTRAINT "uq_stocks_item_loc_batch"';
            END IF;
        END $$;
        """
    )
