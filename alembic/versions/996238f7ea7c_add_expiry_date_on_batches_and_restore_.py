"""add expiry_date on batches and restore uq_batches_item_wh_loc_code

Revision ID: 996238f7ea7c
Revises: ccd9671cca84
Create Date: 2025-11-09 21:56:16.526716
"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "996238f7ea7c"
down_revision: Union[str, Sequence[str], None] = "ccd9671cca84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0) 若存在重复 (item_id, warehouse_id, location_id, batch_code)，仅保留最小 id
    op.execute(
        """
        WITH dups AS (
            SELECT MIN(id) AS keep_id, item_id, warehouse_id, location_id, batch_code
            FROM batches
            GROUP BY item_id, warehouse_id, location_id, batch_code
            HAVING COUNT(*) > 1
        )
        DELETE FROM batches t
        USING dups d
        WHERE t.item_id = d.item_id
          AND t.warehouse_id = d.warehouse_id
          AND t.location_id = d.location_id
          AND t.batch_code = d.batch_code
          AND t.id <> d.keep_id;
        """
    )

    # 1) 增加 expiry_date（若不存在）
    op.execute("ALTER TABLE batches ADD COLUMN IF NOT EXISTS expiry_date DATE")

    # 2) 用 expire_at 旧字段数据填充
    op.execute("UPDATE batches SET expiry_date = COALESCE(expiry_date, expire_at)")

    # 3) 幂等恢复唯一约束 (item_id, warehouse_id, location_id, batch_code)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                  FROM pg_constraint c
                  JOIN pg_class rel ON rel.oid = c.conrelid
                 WHERE c.contype='u'
                   AND c.conname='uq_batches_item_wh_loc_code'
                   AND rel.relname='batches'
            ) THEN
                EXECUTE 'ALTER TABLE "batches"
                         ADD CONSTRAINT "uq_batches_item_wh_loc_code"
                         UNIQUE (item_id, warehouse_id, location_id, batch_code)';
            END IF;
        END $$;
        """
    )

    # 4) FEFO 相关索引（可重复执行）
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_batches_expiry_date" ON batches (expiry_date)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_batches_batch_code" ON batches (batch_code)'
    )


def downgrade() -> None:
    # 回滚：删除索引 + 唯一约束 + 列
    op.execute('DROP INDEX IF EXISTS "ix_batches_batch_code"')
    op.execute('DROP INDEX IF EXISTS "ix_batches_expiry_date"')
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                  FROM pg_constraint c
                  JOIN pg_class rel ON rel.oid = c.conrelid
                 WHERE c.contype='u'
                   AND c.conname='uq_batches_item_wh_loc_code'
                   AND rel.relname='batches'
            ) THEN
                EXECUTE 'ALTER TABLE "batches"
                         DROP CONSTRAINT "uq_batches_item_wh_loc_code"';
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE batches DROP COLUMN IF EXISTS expiry_date")
