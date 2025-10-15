"""add unique (reason, ref, ref_line) on stock_ledger, with putaway fixup

Revision ID: 20251014_uq_ledger_reason_ref_refline
Revises: 737276e10020
Create Date: 2025-10-14
"""

from alembic import op

revision = "20251014_uq_ledger_reason_ref_refline"
down_revision = "737276e10020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 将 ref_line 从 varchar 改为 integer（非数字/NULL 统一收敛到 1）
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'stock_ledger'
              AND column_name = 'ref_line'
              AND data_type IN ('character varying','text')
          ) THEN
            ALTER TABLE public.stock_ledger
              ALTER COLUMN ref_line TYPE INTEGER
              USING (
                CASE
                  WHEN ref_line ~ '^[0-9]+$' THEN ref_line::int
                  WHEN ref_line IS NULL THEN 1
                  ELSE 1
                END
              );
          END IF;
        END$$;
        """
    )

    # 保证 NOT NULL（如果之前有 NULL，这里已统一为 1）
    op.execute("ALTER TABLE public.stock_ledger ALTER COLUMN ref_line SET NOT NULL;")

    # 2) 对于 PUTAWAY 的重复键（reason,ref,ref_line），右腿 +1 修正入库腿
    #    仅对第二条及之后（rn>1）且 delta>0 的记录做 +1
    op.execute(
        """
        WITH d AS (
          SELECT id, reason, ref, ref_line, delta,
                 ROW_NUMBER() OVER (PARTITION BY reason, ref, ref_line ORDER BY id) AS rn
          FROM public.stock_ledger
          WHERE reason = 'PUTAWAY'
        )
        UPDATE public.stock_ledger AS sl
           SET ref_line = sl.ref_line + 1
          FROM d
         WHERE sl.id = d.id
           AND d.rn > 1
           AND d.delta > 0;
        """
    )

    # 3) 幂等创建 UNIQUE(reason,ref,ref_line)
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM   pg_constraint
            WHERE  conname = 'uq_ledger_reason_ref_refline'
            AND    conrelid = 'public.stock_ledger'::regclass
          ) THEN
            ALTER TABLE public.stock_ledger
              ADD CONSTRAINT uq_ledger_reason_ref_refline
              UNIQUE (reason, ref, ref_line);
          END IF;
        END$$;
        """
    )


def downgrade() -> None:
    # 通常不回滚；如必须可按需删除唯一约束并把列类型改回 varchar(32/..)
    pass
