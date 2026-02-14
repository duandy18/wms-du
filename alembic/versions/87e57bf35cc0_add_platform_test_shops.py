"""add platform_test_shops

Revision ID: 87e57bf35cc0
Revises: d95f7d97126f
Create Date: 2026-02-14 10:58:16.571875

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "87e57bf35cc0"
down_revision: Union[str, Sequence[str], None] = "d95f7d97126f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------- platform_test_shops ----------------
    # 说明：
    # - 不硬编码 store_id（测试库/不同环境 id 不稳定）
    # - store_id 允许为空：可先声明“测试商铺是谁（platform+shop_id）”，后续再补齐 store_id
    op.create_table(
        "platform_test_shops",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("shop_id", sa.String(length=64), nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=True),
        sa.Column("code", sa.String(length=32), nullable=False, server_default="DEFAULT"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            name="fk_platform_test_shops_store_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "platform",
            "code",
            name="uq_platform_test_shops_platform_code",
        ),
        sa.UniqueConstraint(
            "store_id",
            name="uq_platform_test_shops_store_id",
        ),
    )

    op.create_index(
        "ix_platform_test_shops_platform_shop",
        "platform_test_shops",
        ["platform", "shop_id"],
        unique=False,
    )

    # ------------------------------------------------------
    # 预置测试商铺映射（不写死 store_id）：
    # - 先尝试从 stores 按 platform+shop_id 找到 store_id
    # - 找不到就跳过（兼容 test DB seed 差异）
    # ------------------------------------------------------

    # DEMO: shop_id='1'
    op.execute(
        sa.text(
            """
            INSERT INTO platform_test_shops(platform, shop_id, store_id, code)
            SELECT 'DEMO', '1', s.id, 'DEFAULT'
              FROM stores s
             WHERE upper(s.platform) = 'DEMO'
               AND s.shop_id = '1'
             ORDER BY s.id ASC
             LIMIT 1
            ON CONFLICT (platform, code) DO NOTHING
            """
        )
    )

    # TB: shop_id='TEST'
    op.execute(
        sa.text(
            """
            INSERT INTO platform_test_shops(platform, shop_id, store_id, code)
            SELECT 'TB', 'TEST', s.id, 'DEFAULT'
              FROM stores s
             WHERE upper(s.platform) = 'TB'
               AND s.shop_id = 'TEST'
             ORDER BY s.id ASC
             LIMIT 1
            ON CONFLICT (platform, code) DO NOTHING
            """
        )
    )

    # ⚠ PDD 等其它平台的测试商铺，你后续确定后再补一条同结构 INSERT 即可
    #    （或者后面做个管理接口/脚本来写入）


def downgrade() -> None:
    op.drop_index(
        "ix_platform_test_shops_platform_shop",
        table_name="platform_test_shops",
    )
    op.drop_table("platform_test_shops")
