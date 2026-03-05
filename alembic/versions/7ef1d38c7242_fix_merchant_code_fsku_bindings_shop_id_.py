"""fix merchant_code_fsku_bindings shop_id as text

Revision ID: 7ef1d38c7242
Revises: 9771d8d02158
Create Date: 2026-02-10 14:13:40.547585
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7ef1d38c7242"
down_revision: Union[str, Sequence[str], None] = "9771d8d02158"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    将 merchant_code_fsku_bindings.shop_id 从 INTEGER 修正为 TEXT。

    背景：
    - platform / shop_id / merchant_code 是唯一域
    - shop_id 的真实语义是「平台店铺 ID」，本质是字符串
    - resolver / stores.shop_id / ingest 全部按 string 语义处理
    """

    # 1) 先 drop 依赖 shop_id 的索引（否则 ALTER TYPE 会失败）
    op.execute(sa.text("DROP INDEX IF EXISTS ux_mc_fsku_bindings_current"))
    op.drop_index("ix_mc_fsku_bindings_lookup", table_name="merchant_code_fsku_bindings")
    op.drop_index("ix_mc_fsku_bindings_fsku_id", table_name="merchant_code_fsku_bindings")

    # 2) 类型变更：INTEGER -> TEXT
    # USING shop_id::text 保证已有数据可迁移（如 916 -> '916'）
    op.execute(
        sa.text(
            """
            ALTER TABLE merchant_code_fsku_bindings
            ALTER COLUMN shop_id
            TYPE TEXT
            USING shop_id::text
            """
        )
    )

    # 3) 重建索引
    op.create_index(
        "ix_mc_fsku_bindings_lookup",
        "merchant_code_fsku_bindings",
        ["platform", "shop_id", "merchant_code", "effective_to"],
        unique=False,
    )
    op.create_index(
        "ix_mc_fsku_bindings_fsku_id",
        "merchant_code_fsku_bindings",
        ["fsku_id"],
        unique=False,
    )

    # 4) 重建 current 唯一约束（partial index）
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX ux_mc_fsku_bindings_current
            ON merchant_code_fsku_bindings(platform, shop_id, merchant_code)
            WHERE effective_to IS NULL
            """
        )
    )


def downgrade() -> None:
    """
    回滚：TEXT -> INTEGER

    ⚠️ 注意：
    只有当 shop_id 全部是纯数字字符串时才安全。
    若存在非数字 shop_id（例如 'TB_123'），此 downgrade 将失败。
    """

    op.execute(sa.text("DROP INDEX IF EXISTS ux_mc_fsku_bindings_current"))
    op.drop_index("ix_mc_fsku_bindings_lookup", table_name="merchant_code_fsku_bindings")
    op.drop_index("ix_mc_fsku_bindings_fsku_id", table_name="merchant_code_fsku_bindings")

    op.execute(
        sa.text(
            """
            ALTER TABLE merchant_code_fsku_bindings
            ALTER COLUMN shop_id
            TYPE INTEGER
            USING shop_id::integer
            """
        )
    )

    op.create_index(
        "ix_mc_fsku_bindings_lookup",
        "merchant_code_fsku_bindings",
        ["platform", "shop_id", "merchant_code", "effective_to"],
        unique=False,
    )
    op.create_index(
        "ix_mc_fsku_bindings_fsku_id",
        "merchant_code_fsku_bindings",
        ["fsku_id"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX ux_mc_fsku_bindings_current
            ON merchant_code_fsku_bindings(platform, shop_id, merchant_code)
            WHERE effective_to IS NULL
            """
        )
    )
