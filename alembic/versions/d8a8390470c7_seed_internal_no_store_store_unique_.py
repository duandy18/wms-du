"""seed INTERNAL/NO-STORE store + unique (platform, shop_id)

Revision ID: d8a8390470c7
Revises: bbc8ba018cb5
Create Date: 2025-11-07 12:18:47.075530
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d8a8390470c7"
down_revision: Union[str, Sequence[str], None] = "bbc8ba018cb5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "stores"
_UQ = "uq_stores_platform_shop"

# 缺省店铺
_PLATFORM = "INTERNAL"
_SHOP = "NO-STORE"
_NAME = "Internal Placeholder Store"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 0) stores 表必须存在
    if not insp.has_table(_TABLE):
        raise RuntimeError("stores table not found; cannot seed INTERNAL/NO-STORE")

    # 1) 幂等补列：platform / shop_id（若不存在则添加为可空的 varchar）
    bind.execute(sa.text(f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS platform VARCHAR(64)"))
    bind.execute(sa.text(f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS shop_id  VARCHAR(128)"))

    # 2) 唯一约束（若不存在则添加）
    bind.execute(
        sa.text(f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = '{_UQ}'
          ) THEN
            ALTER TABLE {_TABLE}
              ADD CONSTRAINT {_UQ}
              UNIQUE (platform, shop_id);
          END IF;
        END $$;
    """)
    )

    # 3) 种缺省店铺（UPSERT）
    bind.execute(
        sa.text(f"""
            INSERT INTO {_TABLE} (platform, shop_id, name)
            VALUES (:p, :s, :n)
            ON CONFLICT (platform, shop_id) DO NOTHING
        """),
        {"p": _PLATFORM, "s": _SHOP, "n": _NAME},
    )


def downgrade() -> None:
    bind = op.get_bind()

    # 删除缺省种子（可选）
    bind.execute(
        sa.text(f"""
            DELETE FROM {_TABLE}
            WHERE platform = :p AND shop_id = :s
        """),
        {"p": _PLATFORM, "s": _SHOP},
    )

    # 去掉唯一约束（不删列，以免影响历史）
    bind.execute(sa.text(f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS {_UQ}"))
