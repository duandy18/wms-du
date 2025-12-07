"""seed NO-STORE for 10 platforms

Revision ID: e547920d161f
Revises: 0c12b25cb6e0
Create Date: 2025-11-07 16:17:20.907475
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "e547920d161f"
down_revision: Union[str, Sequence[str], None] = "0c12b25cb6e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UQ = "uq_stores_platform_shop"
_PLATFORMS = (
    "PDD",
    "TAOBAO",
    "TMALL",
    "JD",
    "RED",  # 小红书
    "DOUYIN",  # 抖音
    "AMAZON",
    "TEMU",
    "SHOPIFY",
    "ALIEXPRESS",  # 速卖通
)


def upgrade() -> None:
    bind = op.get_bind()
    # 1. 确保唯一约束存在
    bind.execute(
        sa.text(f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='{_UQ}') THEN
            ALTER TABLE stores ADD CONSTRAINT {_UQ} UNIQUE (platform, shop_id);
          END IF;
        END $$;
    """)
    )
    # 2. 批量种入 NO-STORE
    for plat in _PLATFORMS:
        bind.execute(
            sa.text("""
                INSERT INTO stores (platform, shop_id, name)
                VALUES (:p, 'NO-STORE', :n)
                ON CONFLICT (platform, shop_id) DO NOTHING
            """),
            {"p": plat, "n": f"{plat} Placeholder Store"},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for plat in _PLATFORMS:
        bind.execute(
            sa.text("DELETE FROM stores WHERE platform=:p AND shop_id='NO-STORE'"),
            {"p": plat},
        )
    # 不删除唯一约束；如需彻底回滚可解开：
    # bind.execute(sa.text(f"ALTER TABLE stores DROP CONSTRAINT IF EXISTS {_UQ}"))
