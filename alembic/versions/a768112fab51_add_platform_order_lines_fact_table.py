"""add platform_order_lines fact table

Revision ID: a768112fab51
Revises: 3175156b20d1
Create Date: 2026-02-07 16:21:32.773799
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a768112fab51"
down_revision: Union[str, Sequence[str], None] = "3175156b20d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 平台订单行事实表：先落事实，再解码（支持外部商铺弱约束）
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_order_lines (
          id              bigserial PRIMARY KEY,

          platform        varchar(50)  NOT NULL,
          shop_id         varchar(128) NOT NULL,
          store_id        integer      NULL,
          ext_order_no    varchar(128) NOT NULL,

          line_no         integer      NOT NULL DEFAULT 1,
          line_key        varchar(300) NOT NULL,

          platform_sku_id varchar(200) NULL,
          qty             integer      NOT NULL,
          title           text         NULL,
          spec            text         NULL,
          extras          jsonb        NULL,
          raw_payload     jsonb        NULL,

          created_at      timestamptz  NOT NULL DEFAULT now(),
          updated_at      timestamptz  NOT NULL DEFAULT now()
        );
        """
    )

    # 幂等：同一平台订单的同一“行键”只能写一条事实
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_platform_order_lines_key
        ON platform_order_lines(platform, shop_id, ext_order_no, line_key);
        """
    )

    # 查询优化：按 store_id 查事实（后续做补绑定/重放）
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_platform_order_lines_store
        ON platform_order_lines(store_id);
        """
    )

    # 查询优化：按订单键查全量行
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_platform_order_lines_order
        ON platform_order_lines(platform, shop_id, ext_order_no);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS platform_order_lines;")
