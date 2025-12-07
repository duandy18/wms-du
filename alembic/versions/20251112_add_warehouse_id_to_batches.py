"""Add warehouse_id to batches; unify unique key; backfill and relink stocks.batch_id

Revision ID: 20251112_add_warehouse_id_to_batches
Revises: 20251112_create_warehouses_if_missing
Create Date: 2025-11-12 13:45:00
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20251112_add_warehouse_id_to_batches"
down_revision: Union[str, Sequence[str], None] = "20251112_create_warehouses_if_missing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # —— 中间内容保持你当前版本一致（已发给你且通过）——
    # 省略：新增/回填 warehouse_id、统一 UQ、补齐缺批次（不写 expire_at）、回填 stocks.batch_id、
    #       添加 fk_batches_warehouse_id / fk_stocks_batch_id（仅在不存在时添加）
    pass


def downgrade() -> None:
    # 回滚：撤销新增的唯一键/索引/FK，最后去掉列
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stocks_batch_id') THEN
        ALTER TABLE stocks DROP CONSTRAINT fk_stocks_batch_id;
      END IF;
    END $$;
    """)
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_batches_item_wh_code') THEN
        ALTER TABLE batches DROP CONSTRAINT uq_batches_item_wh_code;
      END IF;
    END $$;
    """)
    # 关键修正：DROP INDEX IF EXISTS（不是 IF NOT EXISTS）
    op.execute("DROP INDEX IF EXISTS ix_batches_item_wh_code")
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_batches_warehouse_id') THEN
        ALTER TABLE batches DROP CONSTRAINT fk_batches_warehouse_id;
      END IF;
    END $$;
    """)
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='batches' AND column_name='warehouse_id'
      ) THEN
        ALTER TABLE batches DROP COLUMN warehouse_id;
      END IF;
    END $$;
    """)
