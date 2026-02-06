"""create_platform_sku_mirror

Revision ID: de32cf47e987
Revises: a80a5fc82984
Create Date: 2026-02-06 14:46:54.754068
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "de32cf47e987"
down_revision: Union[str, Sequence[str], None] = "a80a5fc82984"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    平台 SKU 镜像（只读事实）：
    - 外部平台同步得到的 PSKU 快照
    - 作为 UI 聚合 / 绑定前线索来源
    - 不参与库存 / 履约 / 业务裁决
    """

    # 使用幂等写法，避免 dev / 脏库重复执行问题
    op.execute(
        """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'platform_sku_mirror'
  ) THEN
    CREATE TABLE public.platform_sku_mirror (
      id               BIGSERIAL PRIMARY KEY,

      platform         VARCHAR(50)  NOT NULL,
      shop_id          BIGINT       NOT NULL,
      platform_sku_id  VARCHAR(200) NOT NULL,

      -- 展示/线索字段（完全只读）
      sku_name         TEXT         NULL,
      spec             TEXT         NULL,

      -- 原始平台 payload（用于审计 / 回溯 / 诊断）
      raw_payload      JSONB        NULL,

      -- 元信息
      source           VARCHAR(50)  NOT NULL,
      observed_at      TIMESTAMPTZ  NOT NULL,
      created_at       TIMESTAMPTZ  NOT NULL,
      updated_at       TIMESTAMPTZ  NOT NULL
    );
  END IF;
END $$;
"""
    )

    # 唯一键：同一平台 + 店铺 + PSKU 只能有一条当前镜像
    op.execute(
        """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'public'
      AND t.relname = 'platform_sku_mirror'
      AND c.conname = 'ux_platform_sku_mirror_key'
  ) THEN
    ALTER TABLE public.platform_sku_mirror
      ADD CONSTRAINT ux_platform_sku_mirror_key
      UNIQUE (platform, shop_id, platform_sku_id);
  END IF;
END $$;
"""
    )


def downgrade() -> None:
    """
    回滚策略：
    - 仅在表存在时 drop
    - 不做数据迁移（镜像表为可再生事实）
    """
    op.execute(
        """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'platform_sku_mirror'
  ) THEN
    DROP TABLE public.platform_sku_mirror;
  END IF;
END $$;
"""
    )
