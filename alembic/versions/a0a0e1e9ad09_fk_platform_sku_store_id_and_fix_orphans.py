"""fk_platform_sku_store_id_and_fix_orphans

Revision ID: a0a0e1e9ad09
Revises: a768112fab51
Create Date: 2026-02-08 10:46:58.720411

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a0a0e1e9ad09"
down_revision: Union[str, Sequence[str], None] = "a768112fab51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase 3.x 收官迁移：

    1) 修复已知孤儿 store_id：
       - PDD + shop_id='1' 的真实 stores.id 是 916
       - 历史数据中存在 store_id=1（stores 表不存在该行）
       - 将 platform_sku_mirror / platform_sku_bindings 中
         platform='PDD' AND store_id=1 的数据迁移到 store_id=916

    2) 强校验：若仍存在任何 platform_sku_* 的 store_id
       在 stores 表中找不到对应行，则迁移失败（避免静默坏数据）

    3) 建立外键约束，防止未来再产生孤儿数据
    """

    # ------------------------------------------------------------------
    # 1) 修复已知孤儿：PDD store_id=1 -> store_id=916
    #    （仅在 916 存在 且 1 不存在 时才执行）
    # ------------------------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM stores WHERE id = 916)
             AND NOT EXISTS (SELECT 1 FROM stores WHERE id = 1)
          THEN
            UPDATE platform_sku_mirror
               SET store_id = 916
             WHERE platform = 'PDD'
               AND store_id = 1;

            UPDATE platform_sku_bindings
               SET store_id = 916
             WHERE platform = 'PDD'
               AND store_id = 1;
          END IF;
        END $$;
        """
    )

    # ------------------------------------------------------------------
    # 2) 强校验：禁止任何 platform_sku_* 再存在孤儿 store_id
    # ------------------------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
              FROM platform_sku_mirror m
              LEFT JOIN stores s ON s.id = m.store_id
             WHERE s.id IS NULL
             LIMIT 1
          ) THEN
            RAISE EXCEPTION
              'orphan store_id exists in platform_sku_mirror (no matching stores.id)';
          END IF;

          IF EXISTS (
            SELECT 1
              FROM platform_sku_bindings b
              LEFT JOIN stores s ON s.id = b.store_id
             WHERE s.id IS NULL
             LIMIT 1
          ) THEN
            RAISE EXCEPTION
              'orphan store_id exists in platform_sku_bindings (no matching stores.id)';
          END IF;
        END $$;
        """
    )

    # ------------------------------------------------------------------
    # 3) 建立外键约束（防止未来再出孤儿）
    # ------------------------------------------------------------------
    op.create_foreign_key(
        "fk_platform_sku_mirror_store_id_stores",
        source_table="platform_sku_mirror",
        referent_table="stores",
        local_cols=["store_id"],
        remote_cols=["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_platform_sku_bindings_store_id_stores",
        source_table="platform_sku_bindings",
        referent_table="stores",
        local_cols=["store_id"],
        remote_cols=["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """
    回滚只移除外键约束，不尝试恢复孤儿数据。
    （孤儿本就不该存在）
    """
    op.drop_constraint(
        "fk_platform_sku_bindings_store_id_stores",
        "platform_sku_bindings",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_platform_sku_mirror_store_id_stores",
        "platform_sku_mirror",
        type_="foreignkey",
    )
