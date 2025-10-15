"""putaway: add uniq(reason,ref,ref_line,stock_id)+check delta!=0

Revision ID: e4b9177afe8d
Revises: 3b1f9c2e1a5b
Create Date: 2025-10-14 07:03:37.504568
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4b9177afe8d"
down_revision: str | Sequence[str] | None = "3b1f9c2e1a5b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "stock_ledger"
UQ_NAME = "uq_ledger_reason_ref_refline_stock"
CK_NAME = "ck_ledger_delta_nonzero"


def upgrade() -> None:
    """Upgrade schema (idempotent, concurrent-safe on PostgreSQL)."""
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # 1) CHECK (delta <> 0) —— 幂等添加 + 按需 VALIDATE
    if is_pg:
        op.execute(
            f"""
DO $$
BEGIN
  -- 若约束不存在则以 NOT VALID 添加
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = '{CK_NAME}'
      AND conrelid = '{TABLE}'::regclass
  ) THEN
    ALTER TABLE {TABLE}
      ADD CONSTRAINT {CK_NAME} CHECK (delta <> 0) NOT VALID;
  END IF;

  -- 若已存在但尚未 VALIDATE，则验证之
  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = '{CK_NAME}'
      AND conrelid = '{TABLE}'::regclass
      AND NOT convalidated
  ) THEN
    ALTER TABLE {TABLE} VALIDATE CONSTRAINT {CK_NAME};
  END IF;
END$$;
"""
        )
    else:
        # SQLite 走 batch_alter_table（重复创建一般会报错，这里假定未创建过）
        with op.batch_alter_table(TABLE) as batch:
            batch.create_check_constraint(CK_NAME, "delta <> 0")

    # 2) 唯一索引 (reason, ref, ref_line, stock_id)
    if is_pg:
        # PG：并发创建 + IF NOT EXISTS，避免锁表与重复报错
        ctx = op.get_context()
        with ctx.autocommit_block():
            op.execute(
                f"""
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {UQ_NAME}
ON {TABLE}(reason, ref, ref_line, stock_id)
"""
            )
    else:
        # SQLite：常规唯一索引
        op.create_index(
            UQ_NAME,
            TABLE,
            ["reason", "ref", "ref_line", "stock_id"],
            unique=True,
        )


def downgrade() -> None:
    """Downgrade schema (idempotent where possible)."""
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # 先删唯一索引
    if is_pg:
        ctx = op.get_context()
        with ctx.autocommit_block():
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {UQ_NAME}")
    else:
        op.drop_index(UQ_NAME, table_name=TABLE)

    # 再删 CHECK 约束
    if is_pg:
        op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CK_NAME};")
    else:
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_constraint(CK_NAME, type_="check")
