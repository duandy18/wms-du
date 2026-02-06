"""fix print_jobs unique constraint

Revision ID: 07be2f2fcab9
Revises: f54c62bbc6bf
Create Date: 2026-02-06 13:08:40.918413
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "07be2f2fcab9"
down_revision: Union[str, Sequence[str], None] = "f54c62bbc6bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CANON = "uq_print_jobs_pick_list_ref"
TABLE = "print_jobs"
INDEX_OLD = "uq_print_jobs_pick_list_ref"
INDEX_RENAMED = "uq_print_jobs_pick_list_ref__idx"


def upgrade() -> None:
    """
    收编 print_jobs 上的 unique index (kind, ref_type, ref_id)
    为正式的 UNIQUE CONSTRAINT，以消除 alembic-check drift。
    """
    op.execute(f"""
DO $$
BEGIN
  -- 1) 如果 UNIQUE CONSTRAINT 已存在，直接结束（幂等）
  IF EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'public'
      AND t.relname = '{TABLE}'
      AND c.contype = 'u'
      AND c.conname = '{CANON}'
  ) THEN
    RETURN;
  END IF;

  -- 2) 如果 unique index 仍与 constraint 同名，先改名避免冲突
  IF EXISTS (
    SELECT 1
    FROM pg_class i
    JOIN pg_namespace n ON n.oid = i.relnamespace
    WHERE n.nspname = 'public'
      AND i.relkind = 'i'
      AND i.relname = '{INDEX_OLD}'
  ) THEN
    EXECUTE 'ALTER INDEX public.{INDEX_OLD} RENAME TO {INDEX_RENAMED}';
  END IF;

  -- 3) 使用 index 收编为 UNIQUE CONSTRAINT
  IF EXISTS (
    SELECT 1
    FROM pg_class i
    JOIN pg_namespace n ON n.oid = i.relnamespace
    WHERE n.nspname = 'public'
      AND i.relkind = 'i'
      AND i.relname = '{INDEX_RENAMED}'
  ) THEN
    EXECUTE
      'ALTER TABLE public.{TABLE} '
      'ADD CONSTRAINT {CANON} UNIQUE USING INDEX {INDEX_RENAMED}';
  ELSE
    -- 极端兜底：index 不存在，直接创建 constraint
    EXECUTE
      'ALTER TABLE public.{TABLE} '
      'ADD CONSTRAINT {CANON} UNIQUE (kind, ref_type, ref_id)';
  END IF;
END $$;
""")


def downgrade() -> None:
    """
    安全回滚：删除 UNIQUE CONSTRAINT（存在才删）
    """
    op.execute(f"""
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'public'
      AND t.relname = '{TABLE}'
      AND c.contype = 'u'
      AND c.conname = '{CANON}'
  ) THEN
    EXECUTE 'ALTER TABLE public.{TABLE} DROP CONSTRAINT {CANON}';
  END IF;

  -- 尝试把 index 名改回（若存在）
  IF EXISTS (
    SELECT 1
    FROM pg_class i
    JOIN pg_namespace n ON n.oid = i.relnamespace
    WHERE n.nspname = 'public'
      AND i.relkind = 'i'
      AND i.relname = '{INDEX_RENAMED}'
  ) AND NOT EXISTS (
    SELECT 1
    FROM pg_class i
    JOIN pg_namespace n ON n.oid = i.relnamespace
    WHERE n.nspname = 'public'
      AND i.relkind = 'i'
      AND i.relname = '{INDEX_OLD}'
  ) THEN
    EXECUTE 'ALTER INDEX public.{INDEX_RENAMED} RENAME TO {INDEX_OLD}';
  END IF;
END $$;
""")
