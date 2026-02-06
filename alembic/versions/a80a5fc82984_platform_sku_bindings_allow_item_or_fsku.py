"""platform_sku_bindings allow item or fsku

Revision ID: a80a5fc82984
Revises: 07be2f2fcab9
Create Date: 2026-02-06 13:42:07.411158

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a80a5fc82984"
down_revision: Union[str, Sequence[str], None] = "07be2f2fcab9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "platform_sku_bindings"
CK_XOR = "ck_platform_sku_bindings_target_xor"
FK_ITEM = "platform_sku_bindings_item_id_fkey"


def upgrade() -> None:
    # 1) fsku_id DROP NOT NULL（幂等）
    op.execute(
        """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='platform_sku_bindings'
      AND column_name='fsku_id'
      AND is_nullable='NO'
  ) THEN
    ALTER TABLE public.platform_sku_bindings
      ALTER COLUMN fsku_id DROP NOT NULL;
  END IF;
END $$;
"""
    )

    # 2) add item_id column（幂等）
    op.execute(
        """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='platform_sku_bindings'
      AND column_name='item_id'
  ) THEN
    ALTER TABLE public.platform_sku_bindings
      ADD COLUMN item_id integer;
  END IF;
END $$;
"""
    )

    # 3) item_id FK（幂等，RESTRICT）
    op.execute(
        f"""
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid=c.conrelid
    JOIN pg_namespace n ON n.oid=t.relnamespace
    WHERE n.nspname='public'
      AND t.relname='{TABLE}'
      AND c.conname='{FK_ITEM}'
  ) THEN
    ALTER TABLE public.{TABLE}
      ADD CONSTRAINT {FK_ITEM}
      FOREIGN KEY (item_id) REFERENCES public.items(id)
      ON DELETE RESTRICT;
  END IF;
END $$;
"""
    )

    # 4) XOR check：恰好一个目标（fsku_id / item_id）
    op.execute(
        f"""
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid=c.conrelid
    JOIN pg_namespace n ON n.oid=t.relnamespace
    WHERE n.nspname='public'
      AND t.relname='{TABLE}'
      AND c.conname='{CK_XOR}'
  ) THEN
    ALTER TABLE public.{TABLE}
      ADD CONSTRAINT {CK_XOR}
      CHECK ( (fsku_id IS NULL) <> (item_id IS NULL) );
  END IF;
END $$;
"""
    )


def downgrade() -> None:
    # 回滚尽量温和：先删 check / fk / column（存在才操作）
    op.execute(
        f"""
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid=c.conrelid
    JOIN pg_namespace n ON n.oid=t.relnamespace
    WHERE n.nspname='public'
      AND t.relname='{TABLE}'
      AND c.conname='{CK_XOR}'
  ) THEN
    ALTER TABLE public.{TABLE} DROP CONSTRAINT {CK_XOR};
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid=c.conrelid
    JOIN pg_namespace n ON n.oid=t.relnamespace
    WHERE n.nspname='public'
      AND t.relname='{TABLE}'
      AND c.conname='{FK_ITEM}'
  ) THEN
    ALTER TABLE public.{TABLE} DROP CONSTRAINT {FK_ITEM};
  END IF;

  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='{TABLE}'
      AND column_name='item_id'
  ) THEN
    ALTER TABLE public.{TABLE} DROP COLUMN item_id;
  END IF;

  -- 不强制把 fsku_id 改回 NOT NULL：回滚可能会遇到 item 绑定数据导致失败
END $$;
"""
    )
