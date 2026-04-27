"""retire_tb_store_platform_code

Revision ID: c7a9e1f42b6d
Revises: a6d9f0b2c4e1
Create Date: 2026-04-27 17:30:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "c7a9e1f42b6d"
down_revision: Union[str, Sequence[str], None] = "a6d9f0b2c4e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 终态平台码收口：
    # - 店铺平台码不再使用 TB 表示淘宝
    # - 淘宝统一使用 TAOBAO
    #
    # 审计确认：
    # - 当前 TB 店铺仅 1 条：store_code=TEST
    # - 迁到 TAOBAO 后不撞 uq_stores_platform_store_code
    # - 平台订单采集凭证、连接、拉单任务中没有 TB 残留
    op.execute(
        """
        UPDATE stores
           SET platform = 'TAOBAO'
         WHERE platform = 'TB'
        """
    )

    # 历史测试店铺表如果存在 TB 记录，也同步收口到 TAOBAO。
    # 该表是 stores 的附属测试店铺映射，不是外部平台码字典。
    op.execute(
        """
        UPDATE platform_test_stores
           SET platform = 'TAOBAO'
         WHERE platform = 'TB'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    # 最小可逆恢复：只恢复本次已知旧测试店铺码。
    # 不把所有 TAOBAO 回滚成 TB，避免误伤已经终态化的淘宝店铺。
    op.execute(
        """
        UPDATE platform_test_stores
           SET platform = 'TB'
         WHERE platform = 'TAOBAO'
           AND store_id IN (
             SELECT id
               FROM stores
              WHERE store_code = 'TEST'
                AND store_name = 'TB-TEST'
           )
        """
    )

    op.execute(
        """
        UPDATE stores
           SET platform = 'TB'
         WHERE platform = 'TAOBAO'
           AND store_code = 'TEST'
           AND store_name = 'TB-TEST'
        """
    )
